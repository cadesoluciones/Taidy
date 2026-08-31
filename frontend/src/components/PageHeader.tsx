import type { ReactNode } from "react";

import { InfoTooltip } from "./InfoTooltip";
import styles from "./PageHeader.module.css";

interface PageHeaderProps {
  title: string;
  /** The paragraph every page used to render under its <h1> -- now behind
   * an (i) button instead of always taking up its own line, so the title
   * sits right under the breadcrumb (already shown in NavShell's top bar)
   * and the page's actual content starts sooner. Omit for a page with
   * nothing worth explaining beyond its title. */
  description?: ReactNode;
  /** Extra buttons next to the title -- e.g. a richer "Ayuda" modal button
   * that doesn't fit InfoTooltip's one-paragraph popover. */
  children?: ReactNode;
}

export function PageHeader({ title, description, children }: PageHeaderProps) {
  return (
    <div className={styles.row}>
      <h1 className={styles.title}>{title}</h1>
      {description && <InfoTooltip text={description} label={`Información sobre "${title}"`} />}
      {children}
    </div>
  );
}
