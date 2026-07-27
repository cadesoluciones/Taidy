import { useMemo } from "react";

import { fetchSchedules, fetchSchedulesWeek } from "../api/schedules";
import { usePolling } from "../hooks/usePolling";
import { ACTION_LABELS } from "./actionLabels";
import styles from "./WeeklyScheduleCalendar.module.css";

const DAY_LABELS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"];

function startOfWeek(reference: Date): Date {
  const mondayIndex = (reference.getDay() + 6) % 7; // getDay(): 0=Sun..6=Sat -> 0=Mon..6=Sun
  const start = new Date(reference);
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - mondayIndex);
  return start;
}

function isSameDay(a: Date, b: Date): boolean {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

interface DayItem {
  time: string;
  label: string;
  scheduleId: string;
}

interface DayColumn {
  date: Date;
  items: DayItem[];
}

/** Week view (Monday-Sunday, local time) of when each enabled schedule is
 * due to fire, built from GET /schedules/week's server-computed occurrences
 * (the exact same APScheduler trigger math the live scheduler fires from)
 * plus GET /schedules for display names. Occurrences are bucketed by their
 * own local calendar date, not assumed to line up 1:1 with the backend's
 * UTC week boundary. */
export function WeeklyScheduleCalendar() {
  const { data: schedulesData } = usePolling(() => fetchSchedules(), 60_000);
  const { data: weekData } = usePolling(() => fetchSchedulesWeek(), 60_000);

  const columns = useMemo<DayColumn[]>(() => {
    const start = startOfWeek(new Date());
    const days: DayColumn[] = Array.from({ length: 7 }, (_, i) => {
      const date = new Date(start);
      date.setDate(start.getDate() + i);
      return { date, items: [] };
    });

    if (!schedulesData || !weekData) return days;

    const schedulesById = new Map(schedulesData.items.map((s) => [s.id, s]));

    for (const [scheduleId, occurrences] of Object.entries(weekData.occurrences)) {
      const schedule = schedulesById.get(scheduleId);
      if (!schedule) continue;
      const label = schedule.name || ACTION_LABELS[schedule.action] || schedule.action;
      for (const iso of occurrences) {
        const when = new Date(iso);
        const column = days.find((d) => isSameDay(d.date, when));
        if (!column) continue;
        column.items.push({
          time: when.toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }),
          label,
          scheduleId,
        });
      }
    }
    for (const day of days) {
      day.items.sort((a, b) => a.time.localeCompare(b.time));
    }
    return days;
  }, [schedulesData, weekData]);

  return (
    <div className={styles.calendar}>
      {columns.map((day, i) => (
        <div className={styles.day} key={day.date.toISOString()}>
          <div className={styles.dayHeader}>
            {DAY_LABELS[i]} {day.date.getDate()}
          </div>
          {day.items.length === 0 ? (
            <p className={styles.empty}>—</p>
          ) : (
            <ul className={styles.items}>
              {day.items.map((item, j) => (
                <li key={j} className={styles.item} title={item.label}>
                  <span className={styles.itemTime}>{item.time}</span> {item.label}
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}
