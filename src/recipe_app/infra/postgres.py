"""The Postgres RecipeRepository (ADR-0005 rule 4, ADR-0007).

Postgres ranks, resumes and limits both tiers, and returns one deck's worth
of recipes. It never evaluates the score formula: it adds up stored integer
weights and indexes score_int in a triangle this process computed with the
domain and sends with each query (ADR-0007 rule 2). The domain then builds
each card, and checks the score Postgres sorted by. Rows become domain
objects through the catalog this process loaded, never through a second
model of a recipe.
"""

import logging
from collections.abc import Sequence
from dataclasses import replace
from typing import Any
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    REAL,
    ColumnElement,
    Integer,
    RowMapping,
    Select,
    Subquery,
    Text,
    Uuid,
    and_,
    any_,
    bindparam,
    case,
    cast,
    exists,
    func,
    literal,
    or_,
    select,
    tuple_,
    union_all,
)
from sqlalchemy.dialects.postgresql import aggregate_order_by
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine
from sqlalchemy.sql.elements import CollectionAggregate, Grouping

from recipe_app.domain.catalog import Diet, IngredientCatalog
from recipe_app.domain.content import Amount, RecipeContent, RecipeWithContent
from recipe_app.domain.cursor import AllStaplesKey, Position, ScoredKey
from recipe_app.domain.matching import (
    AllStaplesMatch,
    Pantry,
    ScoredMatch,
    match_recipe,
)
from recipe_app.domain.ranking import Ranking, SearchFilters, mood_fit, weather_fit
from recipe_app.domain.recipe import Image, PlanAhead, Recipe, RecipeTags
from recipe_app.domain.recipe_search import (
    MIN_SIMILARITY,
    Criterion,
    Found,
    RecipeQuery,
)
from recipe_app.domain.scoring import SCORING_VERSION, score_triangle
from recipe_app.domain.tags import Course, Cuisine, Mood, Weather
from recipe_app.domain.units import Unit
from recipe_app.infra.tables import (
    recipe_ingredients,
    recipe_pairings,
    recipe_search_names,
    recipe_steps,
    recipes,
)

logger = logging.getLogger(__name__)

# Each recipe with its ingredient ids in the order a cook gathers them.
_INGREDIENT_IDS = (
    select(
        func.array_agg(
            aggregate_order_by(
                recipe_ingredients.c.ingredient_id, recipe_ingredients.c.position
            )
        )
    )
    .where(recipe_ingredients.c.recipe_id == recipes.c.id)
    .scalar_subquery()
    .label("ingredient_ids")
)
# Each recipe's pairings in the order written (ADR-0012 rule 8).
_PAIRS = (
    select(
        func.array_agg(
            aggregate_order_by(
                recipe_pairings.c.paired_recipe_id, recipe_pairings.c.position
            )
        )
    )
    .where(recipe_pairings.c.recipe_id == recipes.c.id)
    .scalar_subquery()
    .label("pairs_with")
)
_RECIPE = select(
    recipes.c.id,
    recipes.c.name,
    recipes.c.prep_minutes,
    recipes.c.cook_minutes,
    recipes.c.wait_minutes,
    recipes.c.wait_note,
    recipes.c.image_file,
    recipes.c.image_sha256,
    recipes.c.image_alt,
    recipes.c.cuisine,
    recipes.c.courses,
    recipes.c.moods,
    recipes.c.weather,
    recipes.c.also_known_as,
    _INGREDIENT_IDS,
    _PAIRS,
)

_CONTENT = select(
    recipes.c.serves, recipes.c.image_file, recipes.c.image_sha256, recipes.c.image_alt
)

# The largest core_q any request can give any recipe: every staple unticked.
# Grouped once and joined, not counted per recipe: about half the time.
_UNTICKABLE = (
    select(
        recipe_ingredients.c.recipe_id,
        func.count().label("staples"),
    )
    .where(recipe_ingredients.c.weight == 0)
    .group_by(recipe_ingredients.c.recipe_id)
    .subquery()
)
_MAX_REACHABLE_CORE_Q = select(
    func.max(recipes.c.core_weight + func.coalesce(_UNTICKABLE.c.staples, 0))
).select_from(recipes.outerjoin(_UNTICKABLE, _UNTICKABLE.c.recipe_id == recipes.c.id))


async def reachable_core_q(engine: AsyncEngine) -> int:
    """The largest core_q any search can give a synced recipe (0 when empty)."""
    async with engine.connect() as connection:
        return await connection.scalar(_MAX_REACHABLE_CORE_Q) or 0


class PostgresRecipeRepository:
    """Reads recipes; only `recipe-app db sync` writes them (ADR-0005 rule 2)."""

    def __init__(
        self, engine: AsyncEngine, catalog: IngredientCatalog, *, max_core_q: int
    ) -> None:
        """`max_core_q` sizes the score triangle (ADR-0007 rule 2); `open`
        measures it from the database.
        """
        self._engine = engine
        self._catalog = catalog
        self._scores = score_triangle(max_core_q)

    @classmethod
    async def open(
        cls, engine: AsyncEngine, catalog: IngredientCatalog
    ) -> "PostgresRecipeRepository":
        """Size the triangle at startup, so no search pays for measuring it."""
        reachable = await reachable_core_q(engine)
        # Room for recipes a sync adds before this process restarts.
        max_core_q = max(2 * reachable, 1)
        logger.info("score triangle covers core_q up to %d", max_core_q)
        return cls(engine, catalog, max_core_q=max_core_q)

    async def detail(self, recipe_id: UUID) -> RecipeWithContent | None:
        async with self._engine.connect() as connection:
            # One snapshot, as in ranked: a sync committing between these
            # queries would pair one version's amounts with another's
            # ingredients.
            await connection.execution_options(isolation_level="REPEATABLE READ")
            row = (
                (await connection.execute(_RECIPE.where(recipes.c.id == recipe_id)))
                .mappings()
                .one_or_none()
            )
            recipe = None if row is None else next(iter(self._to_recipes([row])), None)
            if recipe is None:
                return None
            content = await self._content(connection, recipe_id)
            pairs = await self._pairs(connection, recipe.tags.pairs_with)
        return RecipeWithContent(recipe=recipe, content=content, pairs=pairs)

    async def _pairs(
        self, connection: AsyncConnection, pair_ids: tuple[UUID, ...]
    ) -> tuple[Recipe, ...]:
        """The paired recipes in the order written, read in the caller's
        transaction; one this process can't build is left out.
        """
        if not pair_ids:
            return ()
        rows = (
            (
                await connection.execute(
                    _RECIPE.where(recipes.c.id == any_(_uuids("pairs", list(pair_ids))))
                )
            )
            .mappings()
            .all()
        )
        found = {recipe.id: recipe for recipe in self._to_recipes(rows)}
        return tuple(found[pair] for pair in pair_ids if pair in found)

    async def _content(
        self, connection: AsyncConnection, recipe_id: UUID
    ) -> RecipeContent | None:
        """The recipe's content, read in the caller's transaction."""
        row = (
            (await connection.execute(_CONTENT.where(recipes.c.id == recipe_id)))
            .mappings()
            .one_or_none()
        )
        if row is None or row["serves"] is None:
            return None
        amounts = (
            await connection.execute(
                select(recipe_ingredients.c.amount, recipe_ingredients.c.unit)
                .where(recipe_ingredients.c.recipe_id == recipe_id)
                .order_by(recipe_ingredients.c.position)
            )
        ).all()
        steps = await connection.scalars(
            select(recipe_steps.c.text)
            .where(recipe_steps.c.recipe_id == recipe_id)
            .order_by(recipe_steps.c.position)
        )
        return RecipeContent(
            serves=row["serves"],
            amounts=tuple(
                None if unit is None else Amount(value=float(amount), unit=Unit(unit))
                for amount, unit in amounts
            ),
            steps=tuple(steps),
            image=_image(row),
        )

    async def ranked(
        self, pantry: Pantry, filters: SearchFilters, after: Position, limit: int
    ) -> Ranking:
        async with self._engine.connect() as connection:
            # One snapshot, so a sync committing between the queries can't
            # rank with one version of a recipe and build it from another.
            await connection.execution_options(isolation_level="REPEATABLE READ")
            scored = (
                await connection.execute(
                    scored_query(
                        pantry,
                        filters,
                        after.scored,
                        limit,
                        self._scores,
                    )
                )
            ).all()
            all_staples = [
                row.id
                for row in await connection.execute(
                    all_staples_query(pantry, filters, after.all_staples, limit)
                )
            ]
            wanted = [row.id for row in scored] + all_staples
            rows = (
                (
                    await connection.execute(
                        _RECIPE.where(recipes.c.id == any_(_uuids("wanted", wanted)))
                    )
                )
                .mappings()
                .all()
                if wanted
                else []
            )
        found = {recipe.id: recipe for recipe in self._to_recipes(rows)}
        return Ranking(
            scored=self._scored_cards(
                [(row.id, row.score_int) for row in scored], found, pantry, filters
            ),
            all_staples=self._all_staples_cards(all_staples, found, pantry, filters),
        )

    async def find(self, query: RecipeQuery, limit: int, offset: int) -> Found:
        if not query.key:
            return Found(recipes=(), total=0)
        async with self._engine.connect() as connection:
            await connection.execution_options(isolation_level="REPEATABLE READ")
            page = (await connection.execute(find_query(query, limit, offset))).all()
            if page:
                total = page[0].total
            else:
                # Past the last match the window has no row to count on.
                total = await connection.scalar(find_count(query)) or 0
            ids = [row.recipe_id for row in page]
            rows = (
                (
                    await connection.execute(
                        _RECIPE.where(recipes.c.id == any_(_uuids("found", ids)))
                    )
                )
                .mappings()
                .all()
                if ids
                else []
            )
        found = {recipe.id: recipe for recipe in self._to_recipes(rows)}
        return Found(recipes=tuple(found[i] for i in ids if i in found), total=total)

    def _scored_cards(
        self,
        ranked: list[tuple[UUID, int]],
        found: dict[UUID, Recipe],
        pantry: Pantry,
        filters: SearchFilters,
    ) -> tuple[ScoredMatch, ...]:
        """Cards in Postgres's order, each checked by the domain (ADR-0007 rule 5)."""
        cards: list[ScoredMatch] = []
        for recipe_id, score_int in ranked:
            if recipe_id not in found:
                continue  # _to_recipes logged it
            match = match_recipe(found[recipe_id], pantry)
            if not isinstance(match, ScoredMatch):
                self._disagree(recipe_id, f"scored {score_int}", match)
                continue
            if match.score_int != score_int:
                self._disagree(recipe_id, f"scored {score_int}", match.score_int)
                # Keep Postgres's score: the cursor resumes from this card's
                # sort key, so it must be the one Postgres sorted by (rule 5).
                match = replace(match, score_int=score_int)
            # Fit comes from the same stored tags Postgres sorted by.
            cards.append(_fitted(match, filters))
        return tuple(cards)

    def _all_staples_cards(
        self,
        ranked: list[UUID],
        found: dict[UUID, Recipe],
        pantry: Pantry,
        filters: SearchFilters,
    ) -> tuple[AllStaplesMatch, ...]:
        cards: list[AllStaplesMatch] = []
        for recipe_id in ranked:
            if recipe_id not in found:
                continue  # _to_recipes logged it
            match = match_recipe(found[recipe_id], pantry)
            if not isinstance(match, AllStaplesMatch):
                self._disagree(recipe_id, "all staples", match)
                continue
            cards.append(_fitted(match, filters))
        return tuple(cards)

    def _disagree(self, recipe_id: UUID, postgres: str, domain: object) -> None:
        """Postgres and this process weigh a recipe differently: the usual cause
        is a sync that reclassified an ingredient before this pod restarted
        (ADR-0007 risk). Outside that window it is a bug.
        """
        logger.error(
            "recipe %s: postgres ranked it as %s, the domain gives %s "
            "(catalog %s, scoring version %d)",
            recipe_id,
            postgres,
            domain,
            self._catalog.content_hash,
            SCORING_VERSION,
        )

    def _to_recipes(self, rows: Sequence[RowMapping]) -> list[Recipe]:
        """Map rows to recipes, skipping any this process can't build.

        A bad row costs that recipe, never the whole request. The usual cause
        is a sync that added ingredients after this process loaded its catalog;
        those recipes show again after the restart that follows (ADR-0005 risk).
        One warning per call, so a busy pod doesn't log once per recipe.
        """
        found: list[Recipe] = []
        skipped: list[UUID] = []
        missing: set[str] = set()
        for row in rows:
            # array_agg over no rows is NULL; the schema can't forbid that.
            ingredient_ids: list[str] = row["ingredient_ids"] or []
            unknown = {i for i in ingredient_ids if i not in self._catalog.by_id}
            if not ingredient_ids or unknown:
                skipped.append(row["id"])
                missing |= unknown
                continue
            # Built directly: the sync already ran build_recipe's checks on this data.
            found.append(
                Recipe(
                    id=row["id"],
                    name=row["name"],
                    prep_minutes=row["prep_minutes"],
                    cook_minutes=row["cook_minutes"],
                    ingredients=tuple(self._catalog.by_id[i] for i in ingredient_ids),
                    plan_ahead=None
                    if row["wait_minutes"] is None
                    else PlanAhead(
                        wait_minutes=row["wait_minutes"], note=row["wait_note"]
                    ),
                    image=_image(row),
                    tags=_tags(row),
                )
            )
        if skipped:
            logger.warning(
                "skipped %d recipes catalog %s can't build "
                "(no ingredients, or unknown ingredients %s): %s",
                len(skipped),
                self._catalog.content_hash,
                sorted(missing),
                [str(recipe_id) for recipe_id in skipped[:10]],
            )
        return found


def scored_query(
    pantry: Pantry,
    filters: SearchFilters,
    after: ScoredKey | None,
    limit: int,
    scores: list[int],
) -> Select[tuple[UUID, int]]:
    """The scored tier's next `limit` recipes and their score_int, in rank order.

    matched_q adds the stored weights of the ticked ingredients; core_q adds 1
    for each unticked staple to the stored core weight (ADR-0003 rule 1,
    ADR-0007 rule 3). Both come from one read of
    ix_recipe_ingredients_ingredient_id_recipe_id. score_int is
    `scores[core_q * (core_q - 1) / 2 + matched_q]` (scoring.score_triangle);
    past the end it is NULL, ranked last as -1 so the recipe still shows
    (ADR-0007 rule 4). Public so the gate can EXPLAIN exactly this.
    """
    weights = _weights(pantry)
    core_q = recipes.c.core_weight + weights.c.unticked
    # Grouped, so Postgres reads ($1::INTEGER[])[i], not a type INTEGER[][i].
    triangle = Grouping(bindparam("scores", scores, type_=ARRAY(Integer)))
    score = func.coalesce(
        triangle[core_q * (core_q - 1) // 2 + weights.c.matched_q], -1
    ).label("score_int")
    fit = _fit(filters)
    if fit is None:
        # Nothing picked, so every fit is 0: leave it out, and the query is
        # exactly the one ADR-0007 measured.
        query = (
            select(recipes.c.id, score)
            .join(weights, weights.c.recipe_id == recipes.c.id)
            # Scored tier: at least one ticked ingredient (ADR-0003 rule 3).
            .where(weights.c.matched_q > 0, *_filters(filters))
            .order_by(score.desc(), recipes.c.total_minutes, recipes.c.id)
            .limit(limit)
        )
        if after is not None:
            query = query.where(
                tuple_(-score, recipes.c.total_minutes, recipes.c.id)
                > tuple_(*_keyset("after_scored", after, with_fit=False))
            )
        return query

    # Every candidate is scored and sorted anyway, so rank them once in a
    # MATERIALIZED CTE and resume and limit outside it. Inlined, the keyset
    # became a join filter, and Postgres 17 planned that ~30x slower.
    candidates = (
        select(
            recipes.c.id,
            score,
            fit,
            recipes.c.total_minutes,
        )
        .join(weights, weights.c.recipe_id == recipes.c.id)
        .where(weights.c.matched_q > 0, *_filters(filters))
        .cte("candidates")
        .prefix_with("MATERIALIZED")
    )
    c = candidates.c
    query = (
        select(c.id, c.score_int)
        .order_by(c.fit.desc(), c.score_int.desc(), c.total_minutes, c.id)
        .limit(limit)
    )
    if after is not None:
        query = query.where(
            tuple_(-c.fit, -c.score_int, c.total_minutes, c.id)
            > tuple_(*_keyset("after_scored", after, with_fit=True))
        )
    return query


def _fit(filters: SearchFilters) -> ColumnElement[int] | None:
    """The picked moods a recipe has, plus 1 if it suits a picked weather
    (ADR-0012 rule 6); None when nothing is picked and every fit is 0.
    """
    if not filters.ranks_by_fit:
        return None
    parts: list[ColumnElement[int]] = []
    # One CASE per picked mood: a plain expression, no subquery per row.
    parts.extend(
        case((_text_param(f"fit_mood_{n}", mood) == any_(recipes.c.moods), 1), else_=0)
        for n, mood in enumerate(sorted(filters.moods))
    )
    if filters.weather:
        suits = _overlaps(recipes.c.weather, "fit_weather", filters.weather)
        parts.append(case((suits, 1), else_=0))
    return sum(parts[1:], parts[0]).label("fit")


def _fitted[M: (ScoredMatch, AllStaplesMatch)](match: M, filters: SearchFilters) -> M:
    return replace(
        match,
        mood_fit=mood_fit(match.recipe, filters),
        weather_fit=weather_fit(match.recipe, filters),
    )


def _tags(row: RowMapping) -> RecipeTags:
    return RecipeTags(
        cuisine=None if row["cuisine"] is None else Cuisine(row["cuisine"]),
        courses=tuple(Course(value) for value in row["courses"]),
        moods=tuple(Mood(value) for value in row["moods"]),
        weather=tuple(Weather(value) for value in row["weather"]),
        also_known_as=tuple(row["also_known_as"]),
        # array_agg over no rows is NULL.
        pairs_with=tuple(row["pairs_with"] or ()),
    )


def _image(row: RowMapping) -> Image | None:
    if row["image_file"] is None:
        return None
    return Image(
        file=row["image_file"], sha256=row["image_sha256"], alt=row["image_alt"]
    )


def _weights(pantry: Pantry) -> Subquery:
    """matched_q and the unticked staple count of every recipe using a ticked
    or unticked id, in one pass over their rows.

    `have` holds only class A and B ids, which weigh more than 0, and
    `out_of` only staples, which weigh 0 (ADR-0001 rule 3, ADR-0007 rule 3).
    So within these rows the sum of weights is matched_q, and the rows
    weighing 0 are the unticked staples: no row is tested against either
    list twice.
    """
    weight = recipe_ingredients.c.weight
    return (
        select(
            recipe_ingredients.c.recipe_id,
            func.sum(weight).cast(Integer).label("matched_q"),
            func.count().filter(weight == 0).cast(Integer).label("unticked"),
        )
        .where(
            recipe_ingredients.c.ingredient_id
            == _any_text("searched", pantry.have | pantry.out_of)
        )
        .group_by(recipe_ingredients.c.recipe_id)
        .subquery("weights")
    )


def all_staples_query(
    pantry: Pantry, filters: SearchFilters, after: AllStaplesKey | None, limit: int
) -> Select[tuple[UUID]]:
    """The all-staples tier's next `limit` recipes, shortest first (ADR-0003 rule 5).

    All staples, and none of them unticked (rule 3); served by
    ix_recipes_all_staples.
    """
    fit = _fit(filters)
    leading = [] if fit is None else [-fit]
    query = (
        select(recipes.c.id)
        .where(
            recipes.c.all_staples,
            ~exists().where(
                recipe_ingredients.c.recipe_id == recipes.c.id,
                recipe_ingredients.c.ingredient_id
                == _any_text("out_of", pantry.out_of),
            ),
            *_filters(filters),
        )
        .order_by(*leading, recipes.c.total_minutes, recipes.c.id)
        .limit(limit)
    )
    if after is not None:
        query = query.where(
            tuple_(*leading, recipes.c.total_minutes, recipes.c.id)
            > tuple_(*_keyset("after_staples", after, with_fit=fit is not None))
        )
    return query


def _keyset(name: str, key: ScoredKey | AllStaplesKey, *, with_fit: bool) -> list[Any]:
    """The cursor's sort key as bound parameters, one per column. Without
    fit, the key's leading -fit is 0 for every recipe, so it is dropped.
    """
    columns = key if with_fit else key[1:]
    return [bindparam(f"{name}_{n}", value) for n, value in enumerate(columns)]


def _filters(filters: SearchFilters) -> list[ColumnElement[bool]]:
    """The same rules as ranking.passes_filters, on the stored columns."""
    conditions: list[ColumnElement[bool]] = []
    if filters.diet is not None:
        allowed = {diet.value for diet in Diet if filters.diet.allows(diet)}
        conditions.append(recipes.c.diet == _any_text("diets", allowed))
    if filters.max_total_minutes is not None:
        conditions.append(recipes.c.total_minutes <= filters.max_total_minutes)
    if filters.min_total_minutes is not None:
        conditions.append(recipes.c.total_minutes >= filters.min_total_minutes)
    if filters.hidden_recipe_ids:
        hidden = bindparam(
            "hidden", sorted(filters.hidden_recipe_ids), type_=ARRAY(Uuid)
        )
        conditions.append(~(recipes.c.id == any_(hidden)))
    if filters.jain:
        conditions.append(recipes.c.jain)
    if filters.avoid_allergens:
        conditions.append(
            ~_overlaps(recipes.c.allergens, "avoid_allergens", filters.avoid_allergens)
        )
    if filters.avoid_ingredient_ids:
        conditions.append(
            ~exists().where(
                recipe_ingredients.c.recipe_id == recipes.c.id,
                recipe_ingredients.c.ingredient_id
                == _any_text("avoid_ingredients", filters.avoid_ingredient_ids),
            )
        )
    if filters.courses:
        conditions.append(_overlaps(recipes.c.courses, "courses", filters.courses))
    if filters.moods:
        conditions.append(_overlaps(recipes.c.moods, "moods", filters.moods))
    return conditions


def _text_param(name: str, value: str) -> Any:
    return bindparam(name, value, type_=Text)


def _overlaps(
    column: ColumnElement[Any], name: str, values: frozenset[str]
) -> ColumnElement[bool]:
    """`column && :name`: the text[] column shares a value with the list."""
    array = bindparam(name, sorted(values), type_=ARRAY(Text))
    return column.op("&&", is_comparison=True)(array)


def _uuids(name: str, values: list[UUID]) -> Any:
    return bindparam(name, values, type_=ARRAY(Uuid))


def _any_text(
    name: str, values: frozenset[str] | set[str]
) -> CollectionAggregate[bool]:
    """`= ANY(:name)` with one array parameter, so the SQL text stays the same
    whatever the list length and asyncpg's prepared-statement cache keeps hitting.
    """
    return any_(bindparam(name, sorted(values), type_=ARRAY(Text)))


def _matches(query: RecipeQuery) -> Subquery:
    """Each matching recipe once, with its best criterion and, for a close
    spelling, its best similarity (recipe_search.match, in SQL).

    Names and aliases come from ix_recipe_search_names_text_trgm, which
    serves both LIKEs and the % operator. Search keys hold no % or _ (the
    key folds them to spaces), so neither LIKE needs escaping.
    """
    names = recipe_search_names.c
    key = bindparam("q", query.key, type_=Text)
    starts = names.text.like(bindparam("q_prefix", f"{query.key}%", type_=Text))
    word_starts = names.text.like(bindparam("q_word", f"% {query.key}%", type_=Text))
    similarity = func.similarity(names.text, key)
    threshold = cast(MIN_SIMILARITY, REAL)
    criterion = case(
        (and_(names.position == 0, starts), int(Criterion.NAME_STARTS)),
        (or_(starts, word_starts), int(Criterion.WORD_STARTS)),
        else_=int(Criterion.CLOSE_SPELLING),
    )
    no_similarity = cast(0, REAL)
    parts: list[Select[Any]] = [
        select(
            names.recipe_id.label("recipe_id"),
            criterion.label("criterion"),
            case(
                (criterion == int(Criterion.CLOSE_SPELLING), similarity),
                else_=no_similarity,
            ).label("similarity"),
        ).where(
            or_(
                starts,
                word_starts,
                and_(names.text.op("%")(key), similarity >= threshold),
            )
        )
    ]
    other = literal(int(Criterion.INGREDIENT_OR_CUISINE))
    if query.ingredient_ids:
        parts.append(
            select(recipe_ingredients.c.recipe_id, other, no_similarity).where(
                recipe_ingredients.c.ingredient_id
                == _any_text("q_ingredients", query.ingredient_ids)
            )
        )
    if query.cuisines:
        parts.append(
            select(recipes.c.id, other, no_similarity).where(
                recipes.c.cuisine
                == _any_text("q_cuisines", {c.value for c in query.cuisines})
            )
        )
    every = union_all(*parts).subquery("every_match")
    best = func.min(every.c.criterion)
    return (
        select(
            every.c.recipe_id,
            best.label("criterion"),
            case(
                (best == int(Criterion.CLOSE_SPELLING), func.max(every.c.similarity)),
                else_=no_similarity,
            ).label("similarity"),
        )
        .group_by(every.c.recipe_id)
        .subquery("matches")
    )


def find_query(query: RecipeQuery, limit: int, offset: int) -> Select[Any]:
    """One page of recipe search, with the count of every match on each row.

    Sorted as recipe_search.find sorts: criterion, similarity (highest
    first), the name's search key in code point order, id. Public so the
    gate can EXPLAIN exactly this.
    """
    matches = _matches(query)
    name = recipe_search_names.alias("name")
    return (
        select(matches.c.recipe_id, func.count().over().label("total"))
        .join(
            name,
            and_(name.c.recipe_id == matches.c.recipe_id, name.c.position == 0),
        )
        .order_by(
            matches.c.criterion,
            matches.c.similarity.desc(),
            name.c.text.collate("C"),
            matches.c.recipe_id,
        )
        .limit(limit)
        .offset(offset)
    )


def find_count(query: RecipeQuery) -> Select[Any]:
    return select(func.count()).select_from(_matches(query))
