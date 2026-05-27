import { readImageChoiceItems } from "../resolve";
import type { NodeUiControlProps } from "../types";

export function ImageCandidatesControl({ config, node }: NodeUiControlProps) {
  const items = readImageChoiceItems(config, node);
  return (
    <section className="node-ui-readonly">
      <div className="image-gallery">
        {items.map((item) => (
          <img alt={item.label} key={`${item.id}-${item.index}`} src={item.imageUrl} />
        ))}
      </div>
    </section>
  );
}
