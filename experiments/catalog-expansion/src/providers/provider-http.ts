export type FetchImplementation = (
  input: string | URL,
  init?: RequestInit,
) => Promise<Response>;

type ProviderErrorCode =
  | "configuration"
  | "timeout"
  | "request-failed"
  | "http-error"
  | "malformed-response";

export class ProviderError extends Error {
  readonly provider: string;
  readonly code: ProviderErrorCode;

  constructor(provider: string, code: ProviderErrorCode, message: string) {
    super(message);
    this.name = "ProviderError";
    this.provider = provider;
    this.code = code;
  }
}

export async function requestJson(
  provider: string,
  fetchImplementation: FetchImplementation,
  input: string | URL,
  init: RequestInit,
  timeoutMilliseconds: number,
): Promise<unknown> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMilliseconds);

  try {
    const response = await fetchImplementation(input, {
      ...init,
      signal: controller.signal,
    });

    if (!response.ok) {
      throw new ProviderError(
        provider,
        "http-error",
        `${provider} returned HTTP ${response.status}.`,
      );
    }

    try {
      return await response.json();
    } catch {
      throw new ProviderError(
        provider,
        "malformed-response",
        `${provider} returned invalid JSON.`,
      );
    }
  } catch (error) {
    if (error instanceof ProviderError) {
      throw error;
    }

    const timedOut = controller.signal.aborted;
    throw new ProviderError(
      provider,
      timedOut ? "timeout" : "request-failed",
      timedOut
        ? `${provider} timed out after ${timeoutMilliseconds} ms.`
        : `${provider} request failed: ${error instanceof Error ? error.message : String(error)}.`,
    );
  } finally {
    clearTimeout(timeout);
  }
}

export function providerEndpoint(baseUrl: string, path: string): URL {
  return new URL(
    `${baseUrl.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`,
  );
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}
