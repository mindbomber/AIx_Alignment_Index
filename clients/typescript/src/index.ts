import { operations, type OperationId } from './generated.js'

export { operations, type OperationId } from './generated.js'

export class AIxClientError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message)
  }
}

export class AIxClient {
  constructor(
    private readonly baseUrl: string,
    private readonly token?: string,
  ) {}

  async call<T>(
    operationId: OperationId,
    options: {
      path?: Record<string, string>
      query?: Record<string, string | number | boolean>
      body?: unknown
    } = {},
  ): Promise<T> {
    const [method, template] = operations[operationId]
    let route: string = template
    for (const [name, value] of Object.entries(options.path ?? {})) {
      route = route.replace(`{${name}}`, encodeURIComponent(value))
    }
    if (route.includes('{')) throw new Error(`Missing path parameter for ${route}`)
    const url = new URL(route, this.baseUrl)
    for (const [name, value] of Object.entries(options.query ?? {})) {
      url.searchParams.set(name, String(value))
    }
    const response = await fetch(url, {
      method,
      headers: {
        Accept: 'application/json',
        ...(options.body === undefined ? {} : { 'Content-Type': 'application/json' }),
        ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
      },
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
    })
    if (!response.ok) {
      const payload = await response.json().catch(() => ({})) as {
        error?: { code?: string; message?: string }
      }
      throw new AIxClientError(
        response.status,
        payload.error?.code ?? 'request_failed',
        payload.error?.message ?? `Request failed (${response.status})`,
      )
    }
    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
  }
}
