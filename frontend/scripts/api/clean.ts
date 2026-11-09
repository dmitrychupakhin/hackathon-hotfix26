import { cleanGeneratedApi } from "./lib/output";

async function main() {
  if (process.argv.length > 2)
    throw new Error("api:clean does not accept paths or arguments");
  await cleanGeneratedApi();
  console.log(
    "Removed src/shared/api/__generated__. Hand-maintained files preserved.",
  );
}

main().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});
