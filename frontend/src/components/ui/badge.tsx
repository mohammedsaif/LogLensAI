import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium", {
  variants: {
    variant: {
      default: "border-transparent bg-slate-100 text-slate-700",
      teal: "border-transparent bg-teal-50 text-teal-800",
      navy: "border-transparent bg-navy-900 text-white",
      outline: "border-slate-300 text-slate-700",
      dashed: "border-dashed border-slate-400 text-slate-700 bg-white",
      warn: "border-transparent bg-amber-100 text-amber-900",
      danger: "border-transparent bg-red-100 text-red-800",
      critical: "border-transparent bg-rose-100 text-rose-900",
    },
  },
  defaultVariants: { variant: "default" },
});

export interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <span className={cn(badgeVariants({ variant }), className)} {...props} />;
}
