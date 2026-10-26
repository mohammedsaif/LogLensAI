import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const alertVariants = cva("flex gap-3 rounded-lg border px-4 py-3 text-sm [&_svg]:mt-0.5 [&_svg]:size-4 [&_svg]:shrink-0", {
  variants: {
    variant: {
      info: "border-teal-200 bg-teal-50 text-teal-900",
      warn: "border-amber-300 bg-amber-50 text-amber-900",
      error: "border-red-300 bg-red-50 text-red-900",
    },
  },
  defaultVariants: { variant: "info" },
});

export function Alert({
  className,
  variant,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof alertVariants>) {
  return <div role={variant === "error" ? "alert" : "status"} className={cn(alertVariants({ variant }), className)} {...props} />;
}
