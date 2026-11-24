export interface User {
  id: number;
  name: string;
  username: string;
}
export interface Workspace {
  id: string;
  name: string;
  timezone: string;
  opens_at: string;
  closes_at: string;
  role: "manager" | "member";
}
export interface Space {
  id: string;
  name: string;
  kind: string;
  capacity: number;
  floor: string;
  description: string;
  amenities: string[];
  active: boolean;
}
export interface Booking {
  id: string;
  resource: string;
  resource_name: string;
  owner_id: number;
  owner_name: string;
  title: string;
  starts_at: string;
  ends_at: string;
  attendees: number;
  status: "confirmed" | "cancelled";
  can_cancel: boolean;
}
export interface Session {
  user: User | null;
  workspaces: Workspace[];
}
let csrf = "";
export async function request<T>(
  path: string,
  method = "GET",
  body?: unknown,
  key?: string,
): Promise<T> {
  if (method !== "GET" && !csrf)
    csrf = (await request<{ csrfToken: string }>("/csrf/")).csrfToken;
  const response = await fetch("/api" + path, {
    method,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(method !== "GET" ? { "X-CSRFToken": csrf } : {}),
      ...(key ? { "Idempotency-Key": key } : {}),
    },
    ...(body !== undefined ? { body: JSON.stringify(body) } : {}),
  });
  const data = await response.json().catch(() => ({
    detail: "The server could not complete your request. Please try again.",
  }));
  if (!response.ok) {
    const describe = (value: unknown): string =>
      typeof value === "string"
        ? value
        : Array.isArray(value)
          ? value.map(describe).join(" ")
          : value && typeof value === "object"
            ? Object.entries(value)
                .map(
                  ([k, v]) =>
                    `${k === "detail" ? "" : k.replaceAll("_", " ") + ": "}${describe(v)}`,
                )
                .join(" ")
            : "Request failed.";
    throw new Error(describe(data));
  }
  if (data.csrfToken) csrf = data.csrfToken;
  return data as T;
}
export const dayIn = (zone: string) =>
  new Intl.DateTimeFormat("en-CA", {
    timeZone: zone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
export const clock = (iso: string, zone: string) =>
  new Intl.DateTimeFormat("en-GB", {
    timeZone: zone,
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(iso));
