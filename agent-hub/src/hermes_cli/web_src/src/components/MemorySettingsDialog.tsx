import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { Button } from "@nous-research/ui/ui/components/button";
import { Checkbox } from "@nous-research/ui/ui/components/checkbox";
import { Input } from "@nous-research/ui/ui/components/input";
import { Label } from "@nous-research/ui/ui/components/label";
import { Spinner } from "@nous-research/ui/ui/components/spinner";
import { useI18n } from "@/i18n";
import { useModalBehavior } from "@/hooks/useModalBehavior";
import { api, type ProfileMemorySettings } from "@/lib/api";
import { cn, themedBody } from "@/lib/utils";

const DEFAULT_SETTINGS: ProfileMemorySettings = {
  memory_enabled: true,
  user_profile_enabled: true,
  memory_char_limit: 2200,
  user_char_limit: 1375,
  prefetch_limit: 5,
};

export function MemorySettingsDialog({
  open,
  profileId,
  provider,
  onClose,
  onSaved,
}: {
  open: boolean;
  profileId: string;
  provider: string;
  onClose: () => void;
  onSaved: () => void;
}) {
  const { t } = useI18n();
  const modalRef = useModalBehavior({ open, onClose });
  const [settings, setSettings] = useState<ProfileMemorySettings>(DEFAULT_SETTINGS);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeRequest = useRef<string | null>(null);

  const holo = provider === "holographic";
  const p = t.profiles;

  const loadSettings = useCallback(async (name: string) => {
    activeRequest.current = name;
    setLoading(true);
    setError(null);
    try {
      const data = await api.getProfileMemorySettings(name);
      if (activeRequest.current === name) {
        setSettings(data);
      }
    } catch (err) {
      if (activeRequest.current === name) {
        setError(String(err));
      }
    } finally {
      if (activeRequest.current === name) {
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    if (!open || !profileId) return;
    void loadSettings(profileId);
    return () => {
      activeRequest.current = null;
    };
  }, [loadSettings, open, profileId]);

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await api.updateProfileMemorySettings(profileId, settings);
      onSaved();
      onClose();
    } catch (err) {
      setError(String(err));
    } finally {
      setSaving(false);
    }
  };

  if (!open) return null;

  return (
    <div
      ref={modalRef}
      className="fixed inset-0 z-[100] flex items-center justify-center bg-background/85 backdrop-blur-sm p-4"
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="memory-settings-title"
    >
      <div
        className={cn(
          themedBody,
          "relative w-full max-w-lg border border-border bg-card shadow-2xl flex flex-col max-h-[90vh]",
        )}
      >
        <Button
          ghost
          size="icon"
          onClick={onClose}
          className="absolute right-2 top-2 text-muted-foreground hover:text-foreground"
          aria-label={t.common.cancel}
        >
          <X />
        </Button>

        <header className="border-b border-border p-5 pb-3">
          <h2 id="memory-settings-title" className="font-mondwest text-display text-base tracking-wider">
            {p.editMemory ?? "Memory injection"}
            <span className="text-muted-foreground"> · {profileId}</span>
          </h2>
        </header>

        <div className="grid gap-4 overflow-y-auto p-5">
          <p className="text-muted-foreground text-xs">{p.memoryNextSessionHint}</p>

          {loading ? (
            <div className="flex justify-center py-8">
              <Spinner className="h-6 w-6" />
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2">
                <Checkbox
                  id="mem-page-memory-enabled"
                  checked={settings.memory_enabled}
                  onCheckedChange={(checked) =>
                    setSettings((prev) => ({
                      ...prev,
                      memory_enabled: checked === true,
                    }))
                  }
                />
                <Label htmlFor="mem-page-memory-enabled" className="text-sm font-normal">
                  {p.memoryEnabledLabel}
                </Label>
              </div>

              <div className="flex items-center gap-2">
                <Checkbox
                  id="mem-page-user-enabled"
                  checked={settings.user_profile_enabled}
                  onCheckedChange={(checked) =>
                    setSettings((prev) => ({
                      ...prev,
                      user_profile_enabled: checked === true,
                    }))
                  }
                />
                <Label htmlFor="mem-page-user-enabled" className="text-sm font-normal">
                  {p.userProfileEnabledLabel}
                </Label>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="mem-page-memory-limit">{p.memoryCharLimitLabel}</Label>
                  <Input
                    id="mem-page-memory-limit"
                    type="number"
                    min={256}
                    max={50000}
                    value={settings.memory_char_limit}
                    onChange={(e) =>
                      setSettings((prev) => ({
                        ...prev,
                        memory_char_limit: Number(e.target.value) || prev.memory_char_limit,
                      }))
                    }
                  />
                  <p className="text-muted-foreground text-xs">{p.memoryCharLimitHint}</p>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="mem-page-user-limit">{p.userCharLimitLabel}</Label>
                  <Input
                    id="mem-page-user-limit"
                    type="number"
                    min={256}
                    max={50000}
                    value={settings.user_char_limit}
                    onChange={(e) =>
                      setSettings((prev) => ({
                        ...prev,
                        user_char_limit: Number(e.target.value) || prev.user_char_limit,
                      }))
                    }
                  />
                  <p className="text-muted-foreground text-xs">{p.userCharLimitHint}</p>
                </div>
              </div>

              {holo ? (
                <div className="space-y-2">
                  <Label htmlFor="mem-page-prefetch-limit">{p.prefetchLimitLabel}</Label>
                  <Input
                    id="mem-page-prefetch-limit"
                    type="number"
                    min={1}
                    max={50}
                    value={settings.prefetch_limit}
                    onChange={(e) =>
                      setSettings((prev) => ({
                        ...prev,
                        prefetch_limit: Number(e.target.value) || prev.prefetch_limit,
                      }))
                    }
                    className="max-w-xs"
                  />
                  <p className="text-muted-foreground text-xs">{p.prefetchLimitHint}</p>
                </div>
              ) : null}
            </>
          )}

          {error ? <p className="text-destructive text-sm">{error}</p> : null}

          <div className="flex justify-end gap-2">
            <Button outlined size="sm" onClick={onClose} disabled={saving}>
              {t.common.cancel}
            </Button>
            <Button size="sm" className="uppercase" onClick={() => void handleSave()} disabled={saving || loading}>
              {saving ? t.common.saving : t.common.save}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
