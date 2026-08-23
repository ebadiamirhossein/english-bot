import { ComingLater } from "@/components/coming-later";
import { PageHeader } from "@/components/page-header";

export default function MapPage() {
  return (
    <>
      <PageHeader eyebrow="Map" title="The road from B1 to B2.">
        Six stages, twenty-four units, and where you are standing on them.
      </PageHeader>

      <ComingLater
        slice="W9"
        title="What will live here"
        items={[
          "Twenty-four units across six stages, with your dot on the path.",
          "A mastery bar per unit, drawn from real checkpoint results.",
          "Locked units say what opens them — never why you are behind.",
          "The next unit is always one tap away.",
        ]}
      />
    </>
  );
}
