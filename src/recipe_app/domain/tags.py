"""The fixed lists recipes and ingredients are tagged from (ADR-0012 rules 1 and 2).

The values are published ids, like ingredient ids: never rename or reuse one
(ADR-0001 rule 2). The web app owns the labels people read.
"""

from enum import StrEnum


class Cuisine(StrEnum):
    NORTH_INDIAN = "north-indian"
    SOUTH_INDIAN = "south-indian"
    EAST_INDIAN = "east-indian"
    WEST_INDIAN = "west-indian"
    INDO_CHINESE = "indo-chinese"
    STREET_FOOD = "street-food"
    CHINESE = "chinese"
    JAPANESE = "japanese"
    KOREAN = "korean"
    THAI = "thai"
    SOUTHEAST_ASIAN = "southeast-asian"
    MIDDLE_EASTERN = "middle-eastern"
    MEDITERRANEAN = "mediterranean"
    ITALIAN = "italian"
    FRENCH = "french"
    SPANISH_PORTUGUESE = "spanish-portuguese"
    EUROPEAN = "european"
    AMERICAN_BRITISH = "american-british"
    MEXICAN_LATIN = "mexican-latin"
    AFRICAN_CARIBBEAN = "african-caribbean"
    SOUTH_ASIAN = "south-asian"


class Course(StrEnum):
    BREAKFAST = "breakfast"
    SNACKS_STARTERS = "snacks-starters"
    SOUPS = "soups"
    SALADS = "salads"
    MAINS = "mains"
    RICE_BREADS = "rice-breads"
    SIDES = "sides"
    DESSERTS = "desserts"
    DRINKS = "drinks"


class Mood(StrEnum):
    """A flavour the dish is known for, not one that is merely present."""

    SPICY = "spicy"
    TANGY = "tangy"
    SWEET = "sweet"
    SAVOURY = "savoury"
    CREAMY = "creamy"
    SMOKY = "smoky"
    FRESH_HERBY = "fresh-herby"
    COMFORTING = "comforting"
    CRISPY = "crispy"
    SWEET_SOUR = "sweet-sour"
    LIGHT = "light"
    HEARTY = "hearty"


class Weather(StrEnum):
    """How the weather makes you feel; it nudges the order, never filters."""

    COOL_DOWN = "cool-down"
    RAINY_DAY_COSY = "rainy-day-cosy"
    WARMING = "warming"
    JUST_PLEASANT = "just-pleasant"
    GREY_GLOOMY = "grey-gloomy"
    COSY_NIGHT_IN = "cosy-night-in"
    STICKY_SLUGGISH = "sticky-sluggish"
    BREEZY_EVENING = "breezy-evening"
    UNDER_THE_WEATHER = "under-the-weather"


class Allergen(StrEnum):
    """The 14 allergens food labels use."""

    PEANUTS = "peanuts"
    TREE_NUTS = "tree-nuts"
    DAIRY = "dairy"
    EGG = "egg"
    GLUTEN = "gluten"
    SOY = "soy"
    SESAME = "sesame"
    FISH = "fish"
    CRUSTACEANS = "crustaceans"
    MOLLUSCS = "molluscs"
    MUSTARD = "mustard"
    CELERY = "celery"
    SULPHITES = "sulphites"
    LUPIN = "lupin"


MIN_COURSES, MAX_COURSES = 1, 2
MIN_MOODS, MAX_MOODS = 1, 3
MAX_WEATHER = 3
MAX_ALIASES = 5
MAX_ALIAS_LENGTH = 60
MAX_PAIRINGS = 4
