import { NextResponse } from "next/server";
import { z } from "zod";
import { VisionError, extractIngredients } from "@/lib/openrouter";
import { createClient } from "@/lib/supabase/server";

export const runtime = "nodejs";
// Vision calls are slow; the default serverless timeout is not always enough.
export const maxDuration = 60;

const RequestSchema = z.object({
  /** Data URI produced by the client after resizing. */
  imageDataUrl: z
    .string()
    .regex(/^data:image\/(jpeg|jpg|png|webp);base64,/, "Expected a base64 image data URI"),
});

/** ~8MB of base64. The client resizes to max edge 1024, so this is a backstop. */
const MAX_DATA_URL_LENGTH = 8_000_000;

export async function POST(request: Request) {
  const supabase = await createClient();

  // Authenticate before doing anything expensive -- this endpoint spends money
  // per call, so it must never be reachable anonymously.
  const {
    data: { user },
    error: authError,
  } = await supabase.auth.getUser();

  if (authError || !user) {
    return NextResponse.json({ error: "Not signed in." }, { status: 401 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Expected a JSON body." }, { status: 400 });
  }

  const parsed = RequestSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { error: parsed.error.issues.map((i) => i.message).join("; ") },
      { status: 400 },
    );
  }

  if (parsed.data.imageDataUrl.length > MAX_DATA_URL_LENGTH) {
    return NextResponse.json(
      { error: "That image is too large. It should have been resized before upload." },
      { status: 413 },
    );
  }

  try {
    const { extraction, raw, model } = await extractIngredients(parsed.data.imageDataUrl);

    // The audit row is written later, once the meal exists and has an id --
    // see saveMeal in app/log/actions.ts. Returning `raw` here lets that
    // happen without a second model call.
    return NextResponse.json({
      ingredients: extraction.ingredients,
      model,
      raw,
    });
  } catch (error) {
    if (error instanceof VisionError) {
      // Every failure mode degrades to the manual path rather than blocking the
      // log. A meal recorded by hand is worth far more than a meal not
      // recorded because the model was unavailable.
      const status = error.kind === "config" ? 500 : 502;
      console.error(`[analyze-photo] ${error.kind}: ${error.message}`);
      return NextResponse.json(
        {
          error: "Could not read that photo. Add the ingredients manually.",
          detail: error.message,
          recoverable: true,
        },
        { status },
      );
    }

    console.error("[analyze-photo] unexpected", error);
    return NextResponse.json(
      {
        error: "Could not read that photo. Add the ingredients manually.",
        recoverable: true,
      },
      { status: 500 },
    );
  }
}
