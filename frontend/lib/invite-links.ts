function normalizeOrigin(origin?: string | null): string | null {
  if (!origin) {
    return null;
  }

  return origin.replace(/\/+$/g, "");
}

const envCandidateBase = normalizeOrigin(process.env.NEXT_PUBLIC_CANDIDATE_APP_URL ?? null);

export const candidateBaseFromEnv = envCandidateBase;

export function resolveCandidateBase(runtimeOrigin?: string | null): string | null {
  if (envCandidateBase) {
    return envCandidateBase;
  }

  return normalizeOrigin(runtimeOrigin ?? null);
}

export function buildCandidateStartLink(
  token?: string | null,
  runtimeOrigin?: string | null,
): string | null {
  if (!token) {
    return null;
  }

  const base = resolveCandidateBase(runtimeOrigin);
  if (!base) {
    return null;
  }

  return `${base}/candidates/${token}`;
}
