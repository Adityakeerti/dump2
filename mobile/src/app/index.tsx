import { Redirect } from "expo-router";
import { useAuth } from "../auth/AuthContext";

/** Entry router: decides where a cold start lands. */
export default function Index() {
  const { token, user, onboarded } = useAuth();
  if (token && user) {
    return <Redirect href={user.emailVerified ? "/explore" : "/verify"} />;
  }
  return <Redirect href={onboarded ? "/welcome" : "/onboarding"} />;
}
