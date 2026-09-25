"use client";

import { useEffect, useRef, useState } from "react";

import { lexemeImageUrl, type CardImage as CardImageData } from "@/lib/api";

/**
 * W13d — a picturable word's picture, with its credit. PRD §2.6.3.
 *
 * **It ADDS a face and replaces nothing.** `CardFace` draws it on the ANSWER
 * side, under the back and the meaning, so it never answers the question; the
 * sentence context stays exactly where it was.
 *
 * **The credit is part of the picture, not a footnote** — CC BY requires it to
 * be VISIBLE (TASKS' W13d row), so the caption renders whenever the picture
 * does, and the two leave together. The links are inline in a sentence, which
 * is WCAG 2.5.8's inline exception to the target-size rule; the card's own
 * controls keep theirs.
 *
 * **A picture that cannot load is not drawn at all** (TASKS: *"a PWA card that
 * renders a broken image is worse than a card with no image"*). Offline, or on
 * any error, the figure — picture and credit — is removed and the card is the
 * card it was before W13d. `complete && naturalWidth === 0` covers an error
 * that fired before React attached its listener.
 */
export function CardImage({ image }: { image: CardImageData }) {
  const [gone, setGone] = useState(false);
  const ref = useRef<HTMLImageElement>(null);

  useEffect(() => {
    const element = ref.current;
    if (element && element.complete && element.naturalWidth === 0) setGone(true);
  }, []);

  if (gone) return null;

  return (
    <figure className="space-y-2" data-testid="card-image">
      {/* A plain <img>: the bytes come from our API with the learner's cookie
          (`crossOrigin="use-credentials"`, as `AudioButton` does), which
          `next/image`'s optimiser would neither send nor cache. The width and
          height reserve the space, so nothing on the card jumps when it arrives. */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        ref={ref}
        src={lexemeImageUrl(image)}
        alt={image.alt}
        width={image.width}
        height={image.height}
        crossOrigin="use-credentials"
        loading="lazy"
        decoding="async"
        onError={() => setGone(true)}
        className="h-auto w-full max-w-[330px] rounded-xl bg-muted"
      />
      <figcaption
        className="text-xs leading-relaxed text-muted-foreground"
        data-testid="card-image-credit"
      >
        Picture:{" "}
        {image.author ? <span data-testid="card-image-author">{image.author}</span> : null}
        {image.author ? " · " : null}
        {image.licence_url ? (
          <a
            href={image.licence_url}
            target="_blank"
            rel="noopener noreferrer"
            className="underline underline-offset-2"
          >
            {image.licence}
          </a>
        ) : (
          image.licence
        )}
        {" · "}
        <a
          href={image.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="underline underline-offset-2"
        >
          Wikimedia Commons
        </a>
      </figcaption>
    </figure>
  );
}
