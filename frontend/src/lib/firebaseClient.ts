// frontend/src/lib/firebaseClient.ts

// Initialize Firebase app on the client
import { initializeApp, getApps } from "firebase/app";
import { getAuth, GoogleAuthProvider, FacebookAuthProvider } from "firebase/auth";

const firebaseConfig = {
  apiKey: process.env.NEXT_PUBLIC_FB_API_KEY,
  authDomain: process.env.NEXT_PUBLIC_FB_AUTH_DOMAIN,
  projectId: process.env.NEXT_PUBLIC_FB_PROJECT_ID,
  appId: process.env.NEXT_PUBLIC_FB_APP_ID,
};

// Avoid re-initializing in Fast Refresh (Next.js hot reload)
export const firebaseApp =
  getApps().length > 0 ? getApps()[0] : initializeApp(firebaseConfig);

// Auth instance
export const auth = getAuth(firebaseApp);

// Providers
export const googleProvider = new GoogleAuthProvider();
export const facebookProvider = new FacebookAuthProvider();