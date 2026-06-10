import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import { useScroll } from "@/hooks/use-scroll";
import { Button } from "@/components/ui/button";
import { MenuToggleIcon } from "@/components/ui/menu-toggle-icon";

const navLinks = [
  { label: "Decisions", href: "#decisions" },
  { label: "Performance", href: "#performance" },
  { label: "Verify", href: "#verify" },
];

export function NavBar() {
  const [open, setOpen] = useState(false);
  const scrolled = useScroll(60);

  return (
    <header className="fixed top-0 left-0 right-0 z-50 flex justify-center pt-4 px-4">
      <motion.nav
        initial={false}
        animate={{ maxWidth: scrolled ? "480px" : "1200px" }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        className={cn(
          "relative w-full flex items-center justify-between px-5 py-3 transition-all duration-300",
          scrolled
            ? "rounded-full border border-[rgba(243,242,238,0.12)] bg-[rgba(11,11,13,0.72)] backdrop-blur-xl shadow-[0_8px_32px_rgba(0,0,0,0.4)]"
            : "rounded-[20px] border border-[rgba(243,242,238,0.06)] bg-[rgba(11,11,13,0.4)] backdrop-blur-md"
        )}
      >
        {/* Left spacer — balances the right badge so links stay centered */}
        <div className="hidden md:flex flex-1" />

        {/* Desktop links — hidden when pill is narrow to avoid overlap */}
        <ul className={cn(
          "hidden md:flex items-center gap-1 transition-all duration-200",
          scrolled ? "opacity-0 pointer-events-none w-0 overflow-hidden" : ""
        )}>
          {navLinks.map((link) => (
            <li key={link.href}>
              <a
                href={link.href}
                className="px-4 py-1.5 text-sm text-[#8B8D91] hover:text-[#F3F2EE] transition-colors rounded-full hover:bg-[rgba(243,242,238,0.06)]"
              >
                {link.label}
              </a>
            </li>
          ))}
        </ul>

        {/* Live badge — right-aligned, always visible */}
        <div className="hidden md:flex flex-1 items-center justify-end">
          <a
            href="https://explorer.sepolia.mantle.xyz/address/0x1d1fFbC1b5F5E0471f8e8E28eAf007dd24EB4887"
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-mono text-[#0b7bff] border border-[rgba(11,123,255,0.3)] hover:border-[rgba(11,123,255,0.6)] transition-colors whitespace-nowrap"
          >
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-[#0b7bff] opacity-75" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-[#0b7bff]" />
            </span>
            Mantle Live
          </a>
        </div>

        {/* Mobile toggle */}
        <Button
          size="icon"
          variant="ghost"
          onClick={() => setOpen(!open)}
          className="md:hidden text-[#F3F2EE]"
          aria-label="Toggle menu"
        >
          <MenuToggleIcon open={open} className="size-5" duration={300} />
        </Button>
      </motion.nav>

      {/* Mobile menu */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ type: "spring", stiffness: 300, damping: 30 }}
            className="fixed top-20 left-4 right-4 rounded-[20px] border border-[rgba(243,242,238,0.08)] bg-[rgba(11,11,13,0.92)] backdrop-blur-xl p-4 md:hidden z-40"
          >
            <ul className="flex flex-col gap-1">
              {navLinks.map((link) => (
                <li key={link.href}>
                  <a
                    href={link.href}
                    onClick={() => setOpen(false)}
                    className="block px-4 py-3 text-sm text-[#8B8D91] hover:text-[#F3F2EE] hover:bg-[rgba(243,242,238,0.06)] rounded-[12px] transition-colors"
                  >
                    {link.label}
                  </a>
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
}
