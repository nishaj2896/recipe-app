export interface Greeting {
  hello: string;
  meal: string;
}

/** The greeting and the meal the title asks about, from the local time. */
export function greetingFor(date: Date): Greeting {
  const hour = date.getHours();
  if (hour >= 5 && hour < 11) return { hello: "Good morning", meal: "breakfast" };
  if (hour >= 11 && hour < 16) return { hello: "Good afternoon", meal: "lunch" };
  if (hour >= 16 && hour < 22) return { hello: "Good evening", meal: "dinner" };
  return { hello: "Up late", meal: "a midnight snack" };
}
