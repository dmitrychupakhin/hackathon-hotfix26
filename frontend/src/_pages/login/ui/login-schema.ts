import { z } from "zod";
import { zLoginRequest } from "@/shared/api/auth";

export const loginSchema = zLoginRequest.extend({
  email: z.string().trim().pipe(zLoginRequest.shape.email),
});
