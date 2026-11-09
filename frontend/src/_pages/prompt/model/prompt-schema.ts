import type { z } from "zod";
import { zPatchedUpdateRequest } from "@/shared/api/account";

export const promptSchema = zPatchedUpdateRequest
  .pick({ system_prompt: true })
  .required();
export type PromptValues = z.infer<typeof promptSchema>;
