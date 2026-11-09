import { z } from "zod";
import {
  zConfirmRegisterRequest,
  zRegisterRequestWritable,
} from "@/shared/api/registration";

export const registerSchema = zRegisterRequestWritable
  .extend({
    email: z.string().trim().pipe(zRegisterRequestWritable.shape.email),
    code: zConfirmRegisterRequest.shape.code,
  })
  .refine((values) => values.password === values.confirm, {
    path: ["confirm"],
    message: "Пароли не совпадают",
  });

export type RegisterValues = z.input<typeof registerSchema>;
export type RegisterOutput = z.output<typeof registerSchema>;
