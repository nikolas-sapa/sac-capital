import React, { ReactNode } from "react";
import { motion, type Variants } from "framer-motion";
import { cn } from "@/lib/utils";

type PresetType = "fade" | "slide" | "scale" | "blur" | "blur-slide" | "zoom" | "bounce";

type AnimatedGroupProps = {
  children: ReactNode;
  className?: string;
  variants?: { container?: Variants; item?: Variants };
  preset?: PresetType;
};

const defaultContainer: Variants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.1 } },
};

const presets: Record<PresetType, { container: Variants; item: Variants }> = {
  fade: {
    container: defaultContainer,
    item: { hidden: { opacity: 0 }, visible: { opacity: 1 } },
  },
  slide: {
    container: defaultContainer,
    item: { hidden: { opacity: 0, y: 20 }, visible: { opacity: 1, y: 0 } },
  },
  scale: {
    container: defaultContainer,
    item: { hidden: { opacity: 0, scale: 0.8 }, visible: { opacity: 1, scale: 1 } },
  },
  blur: {
    container: defaultContainer,
    item: { hidden: { opacity: 0, filter: "blur(4px)" }, visible: { opacity: 1, filter: "blur(0px)" } },
  },
  "blur-slide": {
    container: defaultContainer,
    item: { hidden: { opacity: 0, filter: "blur(4px)", y: 20 }, visible: { opacity: 1, filter: "blur(0px)", y: 0 } },
  },
  zoom: {
    container: defaultContainer,
    item: {
      hidden: { opacity: 0, scale: 0.5 },
      visible: { opacity: 1, scale: 1, transition: { type: "spring", stiffness: 300, damping: 20 } },
    },
  },
  bounce: {
    container: defaultContainer,
    item: {
      hidden: { opacity: 0, y: -50 },
      visible: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 400, damping: 10 } },
    },
  },
};

export function AnimatedGroup({
  children,
  className,
  variants,
  preset = "fade",
}: AnimatedGroupProps) {
  const selected = presets[preset];
  const containerVariants = variants?.container ?? selected.container;
  const itemVariants = variants?.item ?? selected.item;

  return (
    <motion.div initial="hidden" animate="visible" variants={containerVariants} className={cn(className)}>
      {React.Children.map(children, (child, index) => (
        <motion.div key={index} variants={itemVariants}>
          {child}
        </motion.div>
      ))}
    </motion.div>
  );
}
