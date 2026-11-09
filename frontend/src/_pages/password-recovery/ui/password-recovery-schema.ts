import { z } from "zod";
import { zResetPasswordRequestWritable } from "@/shared/api/account";

export const passwordRecoverySchema = zResetPasswordRequestWritable
  .extend({
    email: z.string().trim().pipe(zResetPasswordRequestWritable.shape.email),
  })
  .refine((values) => values.password === values.confirm, {
    path: ["confirm"],
    message: "Пароли не совпадают",
  });

export type RecoveryInput = z.input<typeof passwordRecoverySchema>;
export type RecoveryValues = z.output<typeof passwordRecoverySchema>;
