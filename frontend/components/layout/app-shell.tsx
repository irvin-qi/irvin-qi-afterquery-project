"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useAdminData } from "@/providers/admin-data-provider";
import { FileCode2, LayoutDashboard, Layers, LogOut, Mail, Calendar } from "lucide-react";
import { useSupabaseAuth } from "@/providers/supabase-provider";

const NAV_LINKS = [
  { href: "/app/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/app/dashboard/assessments", label: "Assessments", icon: Layers },
  { href: "/app/review", label: "Reviews", icon: FileCode2 },
  { href: "/app/scheduling", label: "Scheduling", icon: Calendar },
  { href: "/app/settings/emails", label: "Email Templates", icon: Mail },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { currentAdmin, org, workspaceStatus, loading } = useAdminData();
  const router = useRouter();
  const { signOut, user: supabaseUser } = useSupabaseAuth();
  const [isSigningOut, setIsSigningOut] = useState(false);

  useEffect(() => {
    if (loading) {
      return;
    }
    if (workspaceStatus === "needs_org") {
      router.replace("/app/onboarding");
    } else if (workspaceStatus === "pending_approval") {
      router.replace("/app/forbidden");
    }
  }, [workspaceStatus, loading, router]);

  const displayName = useMemo(() => {
    if (currentAdmin?.name && currentAdmin.name.trim().length > 0) {
      return currentAdmin.name;
    }
    const metadata = supabaseUser?.user_metadata ?? {};
    if (typeof metadata.full_name === "string" && metadata.full_name.trim()) {
      return metadata.full_name.trim();
    }
    if (typeof metadata.name === "string" && metadata.name.trim()) {
      return metadata.name.trim();
    }
    if (currentAdmin?.email) {
      return currentAdmin.email;
    }
    if (supabaseUser?.email) {
      return supabaseUser.email;
    }
    return "Admin";
  }, [currentAdmin, supabaseUser]);

  const handleSignOut = async () => {
    setIsSigningOut(true);
    try {
      await signOut();
    } catch (error) {
      console.error("Failed to sign out", error);
    } finally {
      setIsSigningOut(false);
      router.replace("/app/login");
    }
  };

  if (loading || workspaceStatus === "needs_org" || workspaceStatus === "pending_approval") {
    return (
      <div className="flex min-h-screen items-center justify-center bg-zinc-50">
        <p className="text-sm text-zinc-500">Loading your admin workspace...</p>
      </div>
    );
  }

  if (!org) {
    return null;
  }

  return (
    <div className="flex min-h-screen bg-zinc-50">
      <aside className="hidden w-72 shrink-0 border-r border-zinc-200 bg-white px-6 py-8 lg:block">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs uppercase text-zinc-400">Organization</p>
            <p className="text-lg font-semibold text-zinc-900">{org.name}</p>
          </div>
          <span className="rounded-full bg-blue-100 px-2 py-1 text-xs font-medium text-blue-700">Admin</span>
        </div>
        <nav className="mt-8 space-y-1">
          {NAV_LINKS.map((link) => {
            const Icon = link.icon;
            const isExactMatch = pathname === link.href;
            const isNestedMatch = pathname.startsWith(link.href + "/");
            
            // Check if any more specific link matches to avoid highlighting parent routes
            const hasMoreSpecificMatch = NAV_LINKS.some(
              (otherLink) =>
                otherLink.href !== link.href &&
                otherLink.href.startsWith(link.href) &&
                (pathname === otherLink.href || pathname.startsWith(otherLink.href + "/"))
            );
            
            const isActive = (isExactMatch || isNestedMatch) && !hasMoreSpecificMatch;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium text-zinc-600 transition hover:bg-zinc-100 hover:text-zinc-900",
                  isActive && "bg-zinc-100 text-zinc-900",
                )}
              >
                <Icon className="h-4 w-4" />
                {link.label}
              </Link>
            );
          })}
        </nav>
      </aside>
      <main className="flex-1">
        <header className="flex items-center justify-between border-b border-zinc-200 bg-white px-6 py-4">
          <div>
            <p className="text-sm text-zinc-500">Logged in as</p>
            <p className="font-medium text-zinc-900">{displayName}</p>
          </div>
          <div className="flex items-center gap-3">
            <Button
              variant="outline"
              size="sm"
              className="gap-2"
              type="button"
              onClick={handleSignOut}
              disabled={isSigningOut}
            >
              <LogOut className="h-4 w-4" />
              {isSigningOut ? "Signing out..." : "Sign out"}
            </Button>
          </div>
        </header>
        <div className="px-6 py-8">{children}</div>
      </main>
    </div>
  );
}
