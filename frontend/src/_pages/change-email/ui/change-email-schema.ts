import { z } from "zod";
import { zEmailWithCodeRequest } from "@/shared/api/account";

export const changeEmailSchema = zEmailWithCodeRequest.extend({
  email: z.string().trim().pipe(zEmailWithCodeRequest.shape.email),
  code: z.string().trim().pipe(zEmailWithCodeRequest.shape.code),
});
