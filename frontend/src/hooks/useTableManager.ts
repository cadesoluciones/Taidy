import { useEffect, useState } from "react";

import { ApiError } from "../api/client";

/**
 * Shared state machine behind BcTableManager/FactorialTableManager (and any
 * future admin "add/edit/delete a named config entry" screen): list +
 * reload, add-or-edit form state, delete confirmation. The two existing
 * managers were ~90% identical here and differed only in their fields --
 * this hook carries the orchestration, the components keep their own JSX
 * for the (genuinely different) form fields and list item content.
 */
export function useTableManager<TItem extends { name: string }, TForm extends { name: string }, TInput>({
  fetchAll,
  create,
  update,
  remove,
  emptyForm,
  itemToForm,
  formToInput,
}: {
  fetchAll: () => Promise<{ items: TItem[] }>;
  create: (input: TInput & { name: string }) => Promise<TItem>;
  update: (name: string, input: TInput) => Promise<TItem>;
  remove: (name: string) => Promise<void>;
  emptyForm: TForm;
  itemToForm: (item: TItem) => TForm;
  formToInput: (form: TForm) => { input: TInput } | { error: string };
}) {
  const [items, setItems] = useState<TItem[]>([]);
  const [pendingDelete, setPendingDelete] = useState<TItem | null>(null);
  const [isBusy, setIsBusy] = useState(false);
  const [editingName, setEditingName] = useState<string | null>(null);
  const [form, setForm] = useState<TForm>(emptyForm);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  async function reload() {
    setItems((await fetchAll()).items);
  }

  useEffect(() => {
    void reload();
  }, []);

  function startEdit(item: TItem) {
    setEditingName(item.name);
    setForm(itemToForm(item));
    setError(null);
    setSuccess(null);
  }

  function cancelEdit() {
    setEditingName(null);
    setForm(emptyForm);
  }

  async function submit() {
    setError(null);
    setSuccess(null);
    const result = formToInput(form);
    if ("error" in result) {
      setError(result.error);
      return;
    }
    try {
      if (editingName) {
        await update(editingName, result.input);
        setSuccess(`'${editingName}' actualizada.`);
        cancelEdit();
      } else {
        const created = await create({ ...result.input, name: form.name });
        setSuccess(`'${created.name}' añadida.`);
        setForm(emptyForm);
      }
      await reload();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo guardar.");
    }
  }

  async function confirmDelete() {
    if (!pendingDelete) return;
    setIsBusy(true);
    try {
      await remove(pendingDelete.name);
      if (editingName === pendingDelete.name) cancelEdit();
      await reload();
    } finally {
      setIsBusy(false);
      setPendingDelete(null);
    }
  }

  return {
    items,
    form,
    setForm,
    editingName,
    startEdit,
    cancelEdit,
    submit,
    error,
    success,
    pendingDelete,
    setPendingDelete,
    isBusy,
    confirmDelete,
  };
}
