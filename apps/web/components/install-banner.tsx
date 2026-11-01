"use client";

import { Download, X } from "lucide-react";

export function InstallBanner({
  onInstall,
  onDismiss,
}: {
  onInstall: () => void;
  onDismiss: () => void;
}) {
  return (
    <div className="install-banner">
      <div className="brand-mark" style={{ width: 38, height: 38, borderRadius: 13 }}>
        P
      </div>
      <div className="install-copy">
        <strong>Установить Platon</strong>
        Быстрый доступ с домашнего экрана и push-уведомления.
      </div>
      <button
        type="button"
        className="icon-button"
        onClick={onInstall}
        aria-label="Установить"
        style={{ width: 36, height: 36 }}
      >
        <Download size={16} />
      </button>
      <button
        type="button"
        className="icon-button"
        onClick={onDismiss}
        aria-label="Скрыть"
        style={{ width: 36, height: 36 }}
      >
        <X size={15} />
      </button>
    </div>
  );
}
