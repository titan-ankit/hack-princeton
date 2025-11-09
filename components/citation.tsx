"use client";

import { Button } from "@/components/ui/button";

export function Citation({ url }: { url: string }) {
  return (
    <Button
      variant="outline"
      size="sm"
      className="mt-2"
      asChild
    >
      <a href={url} target="_blank" rel="noopener noreferrer">
        {new URL(url).hostname}
      </a>
    </Button>
  );
}
