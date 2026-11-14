import type { Allergen, Course, Diet, Mood, TimeChoice, Weather } from "../store/device";

/**
 * How the fixed lists read in the app (ADR-0012 rule 1: the web app owns
 * the labels). Each list is in the order the screens show it.
 */

/** The food rules screen's diet choices; Jain is a veg diet plus a flag. */
export type DietChoice = "any" | "egg" | "vegetarian" | "jain" | "vegan";

export const DIET_CHOICES: readonly {
  id: DietChoice;
  label: string;
  short: string;
  hint: string;
}[] = [
  { id: "any", label: "Anything", short: "Any diet", hint: "Meat, fish, eggs and veg" },
  { id: "egg", label: "Vegetarian + egg", short: "Veg + egg", hint: "No meat or fish" },
  {
    id: "vegetarian",
    label: "Vegetarian",
    short: "Veg",
    hint: "No meat, fish or egg",
  },
  {
    id: "jain",
    label: "Jain",
    short: "Jain",
    hint: "Vegetarian, no onion, garlic, root veg or mushroom",
  },
  {
    id: "vegan",
    label: "Vegan",
    short: "Vegan",
    hint: "Nothing from animals, no dairy or honey",
  },
];

/** The stored diet and Jain flag as one choice. */
export function dietChoice(diet: Diet | null, jain: boolean): DietChoice {
  if (jain) return "jain";
  if (diet === null || diet === "non_veg") return "any";
  return diet;
}

/** A choice as the diet and Jain flag the deck request sends. */
export function fromDietChoice(choice: DietChoice): { diet: Diet | null; jain: boolean } {
  if (choice === "any") return { diet: null, jain: false };
  if (choice === "jain") return { diet: "vegetarian", jain: true };
  return { diet: choice, jain: false };
}

export const ALLERGENS: Record<Allergen, string> = {
  peanuts: "Peanuts",
  "tree-nuts": "Tree nuts",
  dairy: "Dairy",
  egg: "Egg",
  gluten: "Gluten",
  soy: "Soy",
  sesame: "Sesame",
  fish: "Fish",
  crustaceans: "Prawns, crab",
  molluscs: "Squid, clams",
  mustard: "Mustard",
  celery: "Celery",
  sulphites: "Sulphites",
  lupin: "Lupin",
};

export const COURSES: Record<Course, string> = {
  breakfast: "Breakfast",
  "snacks-starters": "Snacks and starters",
  soups: "Soups",
  salads: "Salads",
  mains: "Mains",
  "rice-breads": "Rice and breads",
  sides: "Sides",
  desserts: "Desserts",
  drinks: "Drinks",
};

/** Courses as the deck chip names them: one word each. */
export const COURSES_SHORT: Record<Course, string> = {
  breakfast: "Breakfast",
  "snacks-starters": "Snacks",
  soups: "Soups",
  salads: "Salads",
  mains: "Mains",
  "rice-breads": "Rice, breads",
  sides: "Sides",
  desserts: "Desserts",
  drinks: "Drinks",
};

export const MOODS: Record<Mood, string> = {
  spicy: "Spicy",
  tangy: "Tangy",
  sweet: "Sweet",
  savoury: "Savoury",
  creamy: "Creamy",
  smoky: "Smoky",
  "fresh-herby": "Fresh and herby",
  comforting: "Comforting",
  crispy: "Crispy",
  "sweet-sour": "Sweet and sour",
  light: "Light",
  hearty: "Hearty",
};

export const WEATHER: Record<Weather, string> = {
  "cool-down": "Need to cool down",
  "rainy-day-cosy": "Rainy-day cosy",
  warming: "Want something warming",
  "just-pleasant": "Just pleasant",
  "grey-gloomy": "Grey and gloomy",
  "cosy-night-in": "Cosy night in",
  "sticky-sluggish": "Sticky and sluggish",
  "breezy-evening": "Breezy evening",
  "under-the-weather": "Under the weather",
};

/** The badge on a card that suits the one weather picked. */
export const WEATHER_PICKS: Record<Weather, string> = {
  "cool-down": "Cooling pick",
  "rainy-day-cosy": "Rainy-day pick",
  warming: "Warming pick",
  "just-pleasant": "Pleasant-day pick",
  "grey-gloomy": "Grey-day pick",
  "cosy-night-in": "Cosy-night pick",
  "sticky-sluggish": "Sticky-day pick",
  "breezy-evening": "Breezy-evening pick",
  "under-the-weather": "Feel-better pick",
};

export const TIMES: Record<TimeChoice, string> = {
  any: "Any",
  "15": "15 min",
  "30": "30 min",
  "60": "1 hr",
  "over-60": "1 hr+",
};

/** The time choices in order; a record's numeric keys would sort first. */
export const TIME_CHOICES: readonly TimeChoice[] = ["any", "15", "30", "60", "over-60"];

/** The time choice as the deck request's two limits. */
export function timeLimits(time: TimeChoice): {
  min_total_minutes: number | null;
  max_total_minutes: number | null;
} {
  if (time === "any") return { min_total_minutes: null, max_total_minutes: null };
  if (time === "over-60") return { min_total_minutes: 61, max_total_minutes: null };
  return { min_total_minutes: null, max_total_minutes: Number(time) };
}

/**
 * The keys of a label record, in the order they were written. Only for
 * records without numeric keys, which JavaScript lists first.
 */
export const keysOf = <K extends string>(labels: Record<K, string>) =>
  Object.keys(labels) as K[];
