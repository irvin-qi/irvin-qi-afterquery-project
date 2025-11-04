import type { DiffResponse } from "./types";

const CACHE_PREFIX = "diff-cache-";
const CACHE_EXPIRY_MS = 5 * 60 * 1000;

interface CachedDiff {
  data: DiffResponse;
  timestamp: number;
}

function getCacheKey(repoId: string, headBranch: string): string {
  return `${CACHE_PREFIX}${repoId}-${headBranch}`;
}

export function getCachedDiff(repoId: string, headBranch: string): DiffResponse | null {
  if (typeof window === "undefined") return null;

  try {
    const cacheKey = getCacheKey(repoId, headBranch);
    const cached = localStorage.getItem(cacheKey);
    if (!cached) return null;

    const parsed: CachedDiff = JSON.parse(cached);
    if (Date.now() - parsed.timestamp > CACHE_EXPIRY_MS) {
      localStorage.removeItem(cacheKey);
      return null;
    }

    return parsed.data;
  } catch (error) {
    console.warn("Error reading diff cache:", error);
    return null;
  }
}

export function setCachedDiff(repoId: string, headBranch: string, data: DiffResponse): void {
  if (typeof window === "undefined") return;

  try {
    const cacheKey = getCacheKey(repoId, headBranch);
    localStorage.setItem(
      cacheKey,
      JSON.stringify({ data, timestamp: Date.now() })
    );
  } catch (error) {
    console.warn("Error writing diff cache:", error);
  }
}

export function clearDiffCache(repoId?: string, headBranch?: string): void {
  if (typeof window === "undefined") return;

  try {
    if (repoId && headBranch) {
      localStorage.removeItem(getCacheKey(repoId, headBranch));
    } else {
      Object.keys(localStorage)
        .filter((key) => key.startsWith(CACHE_PREFIX))
        .forEach((key) => localStorage.removeItem(key));
    }
  } catch (error) {
    console.warn("Error clearing diff cache:", error);
  }
}

