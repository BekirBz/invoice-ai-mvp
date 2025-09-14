// frontend/src/lib/auth.tsx
import React, { createContext, useContext, useEffect, useState } from "react";
import { firebaseApp } from "./firebaseClient";
import {
  getAuth,
  onAuthStateChanged,
  signInWithPopup,
  GoogleAuthProvider,
  FacebookAuthProvider,
  signOut,
  User,
} from "firebase/auth";
import { syncUser } from "@/lib/api";

// ---- helpers ---------------------------------------------------------------
const API_BASE = process.env.NEXT_PUBLIC_API_BASE as string;

// Build a readable user agent fingerprint (safe & optional)
function getUserAgent(): string | undefined {
  if (typeof navigator === "undefined") return undefined;
  const ua = navigator.userAgent || "";
  const lang = navigator.language || "";
  const plat = (navigator as any).platform || "";
  return `${ua} | ${plat} | ${lang}`.slice(0, 400); // keep it short
}

async function logLogin(uid: string) {
  // Optional endpoint: POST /users/logins
  // If you added it in backend, this will record a login event.
  try {
    await fetch(`${API_BASE}/users/logins`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        userId: uid,
        userAgent: getUserAgent(),
        ts: new Date().toISOString(),
        type: "login",
      }),
    });
  } catch (e) {
    // non-blocking: ignore errors
    console.warn("login log failed:", e);
  }
}

// ---- context ---------------------------------------------------------------
type AuthCtx = {
  user: User | null;
  loading: boolean;
  authBusy: boolean;
  signInGoogle: () => Promise<void>;
  signInFacebook: () => Promise<void>;
  signOutUser: () => Promise<void>;
};

const Ctx = createContext<AuthCtx>({
  user: null,
  loading: true,
  authBusy: false,
  signInGoogle: async () => {},
  signInFacebook: async () => {},
  signOutUser: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [authBusy, setAuthBusy] = useState(false);
  const auth = getAuth(firebaseApp);

  // Subscribe to auth state
  useEffect(() => {
    const unsub = onAuthStateChanged(auth, (u) => {
      setUser(u);
      setLoading(false);
    });
    return () => unsub();
  }, [auth]);

  // Upsert user profile into backend whenever user becomes available/changes
  useEffect(() => {
    if (!user) return;
    syncUser({
      userId: user.uid,
      email: user.email ?? undefined,
      displayName: user.displayName ?? undefined,
      userAgent: getUserAgent(), // include UA for audit/debug
    }).catch((e) => console.warn("user sync error:", e));
  }, [user]);

  async function signInGoogle() {
    if (authBusy) return;
    try {
      setAuthBusy(true);
      const cred = await signInWithPopup(auth, new GoogleAuthProvider());
      // record login (optional endpoint)
      await logLogin(cred.user.uid);
    } catch (err: any) {
      if (
        err?.code !== "auth/cancelled-popup-request" &&
        err?.code !== "auth/popup-closed-by-user"
      ) {
        console.error("Google login failed:", err);
        alert(err?.message || "Google login failed");
      }
    } finally {
      setAuthBusy(false);
    }
  }

  async function signInFacebook() {
    if (authBusy) return;
    try {
      setAuthBusy(true);
      const provider = new FacebookAuthProvider();
      provider.addScope("email"); // optional
      const cred = await signInWithPopup(auth, provider);
      // record login (optional endpoint)
      await logLogin(cred.user.uid);
    } catch (err: any) {
      if (
        err?.code !== "auth/cancelled-popup-request" &&
        err?.code !== "auth/popup-closed-by-user"
      ) {
        console.error("Facebook login failed:", err);
        alert(err?.message || "Facebook login failed");
      }
    } finally {
      setAuthBusy(false);
    }
  }

  async function signOutUser() {
    await signOut(auth);
  }

  return (
    <Ctx.Provider
      value={{ user, loading, authBusy, signInGoogle, signInFacebook, signOutUser }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useAuth() {
  return useContext(Ctx);
}