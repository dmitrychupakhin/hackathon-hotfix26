import SwaggerParser from "@apidevtools/swagger-parser";
import { apiSchemaUrl } from "../../api.config";
import { generateAndPublishApi } from "./lib/generation";

async function main() {
  const schema = await SwaggerParser.bundle(
    process.env.API_SCHEMA_URL ?? apiSchemaUrl,
  );
  await generateAndPublishApi(schema);
}

main().catch((error: unknown) => {
  console.error(error);
  process.exitCode = 1;
});
