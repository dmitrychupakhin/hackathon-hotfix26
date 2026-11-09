import { zUpdatePasswordRequestWritable } from "@/shared/api/account";

export const changePasswordSchema = zUpdatePasswordRequestWritable.refine(
  (values) => values.password === values.confirm,
  { path: ["confirm"], message: "Пароли не совпадают" },
);
