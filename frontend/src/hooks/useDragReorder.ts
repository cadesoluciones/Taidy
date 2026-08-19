import type { DragEvent } from "react";
import { useState } from "react";

/** Native HTML5 drag-and-drop reordering for a list -- no extra dependency.
 * Spread `handlersFor(id)` onto each row's draggable container; on drop,
 * `onReorder` receives the full list of ids in their new order (the caller
 * is responsible for persisting it and updating local state). */
export function useDragReorder<T>(items: T[], getId: (item: T) => string, onReorder: (orderedIds: string[]) => void) {
  const [draggedId, setDraggedId] = useState<string | null>(null);
  const [overId, setOverId] = useState<string | null>(null);

  function handlersFor(id: string) {
    return {
      draggable: true as const,
      onDragStart: (e: DragEvent) => {
        setDraggedId(id);
        e.dataTransfer.effectAllowed = "move";
      },
      onDragOver: (e: DragEvent) => {
        e.preventDefault();
        if (id !== draggedId) setOverId(id);
      },
      onDrop: (e: DragEvent) => {
        e.preventDefault();
        setOverId(null);
        if (!draggedId || draggedId === id) return;
        const ids = items.map(getId);
        const fromIndex = ids.indexOf(draggedId);
        const toIndex = ids.indexOf(id);
        setDraggedId(null);
        if (fromIndex === -1 || toIndex === -1) return;
        const next = [...ids];
        next.splice(fromIndex, 1);
        next.splice(toIndex, 0, draggedId);
        onReorder(next);
      },
      onDragEnd: () => {
        setDraggedId(null);
        setOverId(null);
      },
      "data-dragging": id === draggedId ? "true" : undefined,
      "data-drag-over": id === overId ? "true" : undefined,
    };
  }

  return { handlersFor };
}
