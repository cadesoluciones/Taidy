import { describe, expect, it } from "vitest";

import { extractDetailMessage } from "./client";

describe("extractDetailMessage", () => {
  it("passes through a plain string detail unchanged", () => {
    expect(extractDetailMessage("El usuario 'x' ya existe.")).toEqual({
      message: "El usuario 'x' ya existe.",
      code: undefined,
    });
  });

  it("reads {message, code} detail objects", () => {
    expect(extractDetailMessage({ message: "No autorizado", code: "forbidden" })).toEqual({
      message: "No autorizado",
      code: "forbidden",
    });
  });

  it("translates FastAPI's list-of-validation-errors shape into a readable message", () => {
    // The exact 422 shape FastAPI returns for a CreateUserRequest whose
    // password fails Field(min_length=8) -- reproduced live against the
    // real API. This used to fall through to a useless generic message.
    const detail = [
      {
        type: "string_too_short",
        loc: ["body", "password"],
        msg: "String should have at least 8 characters",
        input: "short",
        ctx: { min_length: 8 },
      },
    ];
    const result = extractDetailMessage(detail);
    expect(result.message).toBe("Contraseña: String should have at least 8 characters");
  });

  it("joins multiple validation errors and falls back to the raw field name when unmapped", () => {
    const detail = [
      { loc: ["body", "password"], msg: "String should have at least 8 characters" },
      { loc: ["body", "some_new_field"], msg: "Field required" },
    ];
    const result = extractDetailMessage(detail);
    expect(result.message).toBe("Contraseña: String should have at least 8 characters · some_new_field: Field required");
  });

  it("falls back to a generic message when detail is null or an unrecognized shape", () => {
    expect(extractDetailMessage(null)).toEqual({ message: "Ha ocurrido un error inesperado.", code: undefined });
    expect(extractDetailMessage(42)).toEqual({ message: "Ha ocurrido un error inesperado.", code: undefined });
    expect(extractDetailMessage([])).toEqual({ message: "Ha ocurrido un error inesperado.", code: undefined });
  });
});
