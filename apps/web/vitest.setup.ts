import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// The API origin is read at module load in `lib/env.ts`; tests never reach the
// network (every request is a stub), but an unset variable would make the
// assertion messages read "http://localhost:8000" and hide which host was
// meant.
process.env.NEXT_PUBLIC_API_URL = "http://api.test";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});
