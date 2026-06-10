import { FC } from "react";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  label: string;
  variant?: "primary" | "secondary";
  classes?: string;
  onClick?: () => void;
}

const MotionButton: FC<Props> = ({ label, classes, onClick }) => {
  return (
    <button
      onClick={onClick}
      className={cn(
        "bg-[#1A1A1E] group relative h-auto w-50 cursor-pointer rounded-full border-none p-1 outline-none",
        classes
      )}
    >
      <span
        className="block h-12 w-12 overflow-hidden rounded-full bg-[#0b7bff] duration-500 group-hover:w-full"
        aria-hidden="true"
      />
      <div className="absolute top-1/2 left-4 translate-x-0 -translate-y-1/2 duration-500 group-hover:translate-x-[0.4rem]">
        <ArrowRight className="text-[#F3F2EE] size-6" />
      </div>
      <span
        className="absolute top-2/4 left-2/4 ml-4 -translate-x-2/4 -translate-y-2/4 whitespace-nowrap text-center text-lg font-medium tracking-tight text-[#F3F2EE] duration-500 group-hover:text-[#F3F2EE]"
        style={{ fontFamily: "var(--font-body)" }}
      >
        {label}
      </span>
    </button>
  );
};

export default MotionButton;
