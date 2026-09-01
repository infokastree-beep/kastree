/** Build-time flag: Clerk is enabled only when env is exactly the string "true". */
export const clerkReady = process.env.NEXT_PUBLIC_CLERK_READY === "true";
