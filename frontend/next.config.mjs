/** @type {import('next').NextConfig} */
const gitSha = (
  process.env.VERCEL_GIT_COMMIT_SHA ||
  process.env.NEXT_PUBLIC_GIT_SHA ||
  process.env.GITHUB_SHA ||
  "dev"
).trim();

const nextConfig = {
  reactStrictMode: true,
  // Bake the commit SHA into the client bundle so CI can confirm www.kastree.ie
  // is serving the pushed commit (meta[name=kastree-git-sha] on every page).
  env: {
    NEXT_PUBLIC_GIT_SHA: gitSha,
  },
};

export default nextConfig;
