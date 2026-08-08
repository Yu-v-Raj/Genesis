export class GenesisApiError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "GenesisApiError";
    this.status = status;
  }
}

/** Shared typed JSON transport for Genesis browser API adapters. */
export async function requestJson<T>(
  baseUrl: string,
  endpoint: string,
  init: RequestInit,
  unavailableMessage: string,
  createError: (message: string, status?: number) => Error
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${endpoint}`, {
      ...init,
      headers: { Accept: "application/json", ...init.headers },
      cache: "no-store",
      credentials: "same-origin",
    });
  } catch {
    throw createError(unavailableMessage);
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status} ${response.statusText}).`;
    try {
      const body: unknown = await response.json();
      if (
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof body.detail === "string"
      ) {
        detail = body.detail;
      }
    } catch {
      // Stable response fallback when an upstream error is not JSON.
    }
    throw createError(detail, response.status);
  }

  return response.json() as Promise<T>;
}
