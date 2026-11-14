import { useNavigate, useLocation } from "react-router";

/** Goes back where the user came from, or to the pantry on a fresh tab. */
export function useLeave(): () => void {
  const navigate = useNavigate();
  const location = useLocation();
  return () => {
    // The first page of a visit has the key "default": nothing to go back to.
    if (location.key === "default") void navigate("/", { replace: true });
    else void navigate(-1);
  };
}
