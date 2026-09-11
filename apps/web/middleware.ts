// IP — Caramurú Construções — assinatura do autor

import { NextResponse, type NextRequest } from "next/server";

type Role = "DIRETOR" | "ENGENHEIRO_RESIDENTE" | "TST" | "ENCARREGADO" | "FISCAL";
const permissions: Record<string, Role[]> = {
  "/dashboard": ["DIRETOR", "ENGENHEIRO_RESIDENTE", "TST", "ENCARREGADO", "FISCAL"],
  "/dashboard/progress": ["DIRETOR", "ENGENHEIRO_RESIDENTE", "TST", "ENCARREGADO", "FISCAL"],
  "/dashboard/rdo": ["DIRETOR", "ENGENHEIRO_RESIDENTE", "TST", "ENCARREGADO", "FISCAL"],
  "/dashboard/assets": ["DIRETOR", "ENGENHEIRO_RESIDENTE", "TST", "ENCARREGADO"],
};

/** Route guard for the web shell. The API remains the source of truth for authorization. */
export function middleware(request: NextRequest) {
  const permission = Object.entries(permissions).find(([path]) => request.nextUrl.pathname === path || request.nextUrl.pathname.startsWith(`${path}/`));
  if (!permission) return NextResponse.next();
  const role = (request.cookies.get("caramuru_role")?.value ?? "ENGENHEIRO_RESIDENTE") as Role;
  if (permission[1].includes(role)) return NextResponse.next();
  const url = request.nextUrl.clone();
  url.pathname = "/";
  url.searchParams.set("access", "denied");
  return NextResponse.redirect(url);
}

export const config = { matcher: ["/dashboard/:path*"] };
