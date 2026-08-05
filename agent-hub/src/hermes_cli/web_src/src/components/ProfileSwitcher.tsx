import { Users } from "lucide-react";
import { useProfileScope } from "@/contexts/useProfileScope";
import { useI18n } from "@/i18n";
import { cn } from "@/lib/utils";

/**
 * The machine dashboard's single write-target selector.
 *
 * Rendered in the sidebar above the nav. Config/Keys/Models and other
 * profile-scoped pages read/write the selected profile via fetchJSON
 * ?profile= injection. Skills/MCP/Channels 为全局（HUB_DATA_DIR 根）。
 */
export function ProfileSwitcher({ collapsed }: { collapsed?: boolean }) {
  const { profile, currentProfile, profiles, setProfile } = useProfileScope();
  const { t } = useI18n();

  if (profiles.length < 2) return null;

  const selectValue = profile === "default" ? "" : profile;
  const namedProfiles = profiles.filter(
    (name) => name !== "default" && name !== currentProfile,
  );
  const managed = selectValue || currentProfile || "default";
  const isOther = !!selectValue && selectValue !== currentProfile;

  return (
    <div
      className={cn(
        "flex items-center gap-2 border-b border-current/10 px-3 py-2",
        collapsed && "lg:justify-center lg:px-0",
      )}
      title={t.app.managingProfile ?? "Managing profile"}
    >
      <Users
        className={cn(
          "h-3.5 w-3.5 shrink-0",
          isOther ? "text-amber-300" : "text-text-tertiary",
        )}
      />
      <select
        aria-label={t.app.managingProfile ?? "Managing profile"}
        className={cn(
          "h-7 w-full min-w-0 rounded-none border bg-background px-1 text-xs",
          isOther
            ? "border-amber-500/50 text-amber-300"
            : "border-border text-text-secondary",
          collapsed && "lg:hidden",
        )}
        value={selectValue}
        onChange={(e) => setProfile(e.target.value)}
      >
        <option value="">
          {t.app.integratedDefaultOption ?? "default (global)"}
        </option>
        {namedProfiles.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
      </select>
      {collapsed && (
        <span className="sr-only">{managed}</span>
      )}
    </div>
  );
}
