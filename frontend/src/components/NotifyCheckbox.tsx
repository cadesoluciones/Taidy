import { Mail } from "lucide-react";

import formStyles from "./Form.module.css";

interface NotifyCheckboxProps {
  checked: boolean;
  onChange: (checked: boolean) => void;
}

export function NotifyCheckbox({ checked, onChange }: NotifyCheckboxProps) {
  return (
    <label className={formStyles.checkboxField}>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
        <Mail size={14} /> Avisar por email a los administradores al terminar
      </span>
    </label>
  );
}
