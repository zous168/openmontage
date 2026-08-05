/**
 * AuthWidget — sidebar "Logged in as …" affordance.
 *
 * 一体部署下 ``GET /api/auth/me`` 由组合根返回 ai_worker 设备身份；
 * 独立 Hermes OAuth 门禁时仍由 hermes_cli 返回 Portal session。
 */

import { useEffect, useState } from "react";
import { api, type AuthMeResponse } from "@/lib/api";
import { cn } from "@/lib/utils";
import { LogOut } from "lucide-react";

interface AuthWidgetProps {
  className?: string;
}

function truncateUserId(id: string): string {
  if (id.length <= 14) return id;
  return `${id.slice(0, 14)}…`;
}

export function AuthWidget({ className }: AuthWidgetProps) {
  const [me, setMe] = useState<AuthMeResponse | null>(null);
  const [hidden, setHidden] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    api
      .getAuthMe()
      .then((data) => {
        if (cancelled) return;
        setMe(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.startsWith("401:") || msg.startsWith("403:")) {
          setHidden(true);
          return;
        }
        setError("auth status unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (hidden) return null;

  if (error) {
    return (
      <div
        className={cn(
          "px-5 py-2 text-xs font-sans tracking-normal text-muted-foreground/70",
          className,
        )}
      >
        {error}
      </div>
    );
  }

  if (!me) {
    return (
      <div
        className={cn(
          "h-9 px-5 py-2 text-xs font-sans text-muted-foreground/40",
          className,
        )}
        aria-busy="true"
      >
        …
      </div>
    );
  }

  const handleLogout = () => {
    if (me.provider === "ai_worker") {
      void api.deviceLogout();
    } else {
      void api.logout();
    }
  };

  const label =
    me.display_name || me.email || truncateUserId(me.user_id);
  const tenantName =
    typeof me.tenant_name === "string" && me.tenant_name ? me.tenant_name : "";
  const subtitle =
    me.provider === "ai_worker"
      ? tenantName || "ai_worker"
      : `via ${me.provider}`;

  return (
    <div
      className={cn(
        "flex shrink-0 items-center justify-between gap-2",
        "px-5 py-2",
        "border-t border-current/10",
        "text-xs font-sans tracking-normal",
        className,
      )}
      role="status"
      aria-label={`Logged in as ${label}`}
    >
      <div className="flex min-w-0 flex-col">
        <span className="truncate font-mono text-foreground/90" title={me.user_id}>
          {label}
        </span>
        <span className="truncate text-muted-foreground/70">{subtitle}</span>
      </div>
      <button
        type="button"
        onClick={handleLogout}
        className={cn(
          "shrink-0 rounded p-1.5 text-muted-foreground/70",
          "transition-colors hover:bg-current/10 hover:text-foreground",
          "focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-current/40",
        )}
        aria-label="Log out"
        title="Log out"
      >
        <LogOut className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
