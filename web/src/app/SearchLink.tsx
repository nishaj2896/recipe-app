import { Link } from "react-router";

/** The round search button on the deck and the cookbook (ADR-0012 rule 10). */
export function SearchLink({ className }: { className: string | undefined }) {
  return (
    <Link to="/search" className={className} aria-label="Search recipes">
      <svg
        width="18"
        height="18"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        aria-hidden="true"
      >
        <circle cx="11" cy="11" r="7" />
        <path d="M20 20l-4-4" />
      </svg>
    </Link>
  );
}
