import "server-only";

import { createHmac, timingSafeEqual } from "node:crypto";
import type { NextRequest, NextResponse } from "next/server";

export const adminCookieName = "indiankumbh_admin_session";
const sessionLifetimeSeconds = 8 * 60 * 60;

export function isAdminConfigured() {
  return Boolean(process.env.ADMIN_PASSWORD);
}

export function verifyAdminPassword(password: string) {
  const expected = process.env.ADMIN_PASSWORD || "";
  if (!expected || password.length !== expected.length) return false;
  return timingSafeEqual(Buffer.from(password), Buffer.from(expected));
}

export function createAdminSessionToken() {
  const expiresAt = Math.floor(Date.now() / 1000) + sessionLifetimeSeconds;
  const payload = String(expiresAt);
  return `${payload}.${sign(payload)}`;
}

export function isValidAdminSession(token?: string) {
  if (!token || !process.env.ADMIN_PASSWORD) return false;
  const [expiresAt, signature] = token.split(".");
  if (!expiresAt || !signature || Number(expiresAt) < Math.floor(Date.now() / 1000)) return false;
  const expected = sign(expiresAt);
  if (signature.length !== expected.length) return false;
  return timingSafeEqual(Buffer.from(signature), Buffer.from(expected));
}

export function requestHasAdminSession(request: NextRequest) {
  return isValidAdminSession(request.cookies.get(adminCookieName)?.value);
}

export function setAdminSessionCookie(response: NextResponse) {
  response.cookies.set(adminCookieName, createAdminSessionToken(), {
    httpOnly: true,
    sameSite: "strict",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    maxAge: sessionLifetimeSeconds,
  });
}

function sign(payload: string) {
  return createHmac("sha256", process.env.ADMIN_PASSWORD || "unconfigured").update(payload).digest("hex");
}

