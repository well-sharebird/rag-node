import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"

import { cn } from "@/lib/utils"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        "h-11 w-full min-w-0 rounded-xl border border-[#e5e5e5] bg-[#fafafa] px-3 py-2 text-[14px] transition-all outline-none placeholder:text-[#c7c7c7] focus-visible:border-[#1a1a1a] focus-visible:bg-white focus-visible:ring-2 focus-visible:ring-[#1a1a1a]/5 disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-[#f5f5f5] disabled:opacity-50 md:text-sm",
        className
      )}
      {...props}
    />
  )
}

export { Input }
