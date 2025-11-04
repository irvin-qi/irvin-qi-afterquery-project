import { AdminDataProvider } from "@/providers/admin-data-provider";
import { AppShell } from "@/components/layout/app-shell";
import { AdminAuthGate } from "@/components/auth/admin-auth-gate";

export default function AdminAppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AdminAuthGate>
      <AdminDataProvider>
        <AppShell>{children}</AppShell>
      </AdminDataProvider>
    </AdminAuthGate>
  );
}
