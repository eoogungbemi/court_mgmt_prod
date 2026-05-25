import { NextRequest, NextResponse } from "next/server";
import { jwtVerify }                 from "jose";

const PUBLIC_PATHS  = ["/login", "/health", "/landing.html"];
const SECRET        = new TextEncoder().encode(
  process.env.JWT_SECRET ?? "dev-secret-change-me-in-production"
);

const ROLE_ALLOWED: Record<string, string[]> = {
  "/clerk":      ["clerk", "admin"],
  "/attorney":   ["attorney", "admin"],
  "/judge":      ["judge", "admin"],
  "/admin":      ["admin"],
  "/analytics":  ["clerk", "judge", "admin"],
  "/cases":      ["clerk", "judge", "attorney", "admin"],
};

export async function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Pass-through: public routes, Next internals, static files
  if (
    PUBLIC_PATHS.some((p) => pathname.startsWith(p)) ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/api")
  ) {
    return NextResponse.next();
  }

  // Root → redirect based on role (or to /queue if unauthenticated)
  const token = req.cookies.get("access_token")?.value;

  if (!token) {
    const url = req.nextUrl.clone();
    if (pathname === "/") {
      url.pathname = "/landing.html";
    } else {
      url.pathname = "/login";
      url.searchParams.set("next", pathname);
    }
    return NextResponse.redirect(url);
  }

  try {
    const { payload } = await jwtVerify(token, SECRET, { algorithms: ["HS256"] });
    const role = payload.role as string;

    // Root redirect
    if (pathname === "/") {
      const url = req.nextUrl.clone();
      url.pathname = { admin: "/admin", clerk: "/clerk", attorney: "/attorney", judge: "/judge", public: "/queue" }[role] ?? "/queue";
      return NextResponse.redirect(url);
    }

    // Role guard
    for (const [prefix, allowed] of Object.entries(ROLE_ALLOWED)) {
      if (pathname.startsWith(prefix) && !allowed.includes(role)) {
        const url = req.nextUrl.clone();
        url.pathname = "/queue";
        return NextResponse.redirect(url);
      }
    }

    return NextResponse.next();
  } catch {
    // Expired or invalid token → try to refresh via the backend, then redirect
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    const res = NextResponse.redirect(url);
    res.cookies.delete("access_token");
    return res;
  }
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
