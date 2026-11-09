import { createCn } from "cn/config";

// Register project text sizes so they don't conflict with text color utilities.
const cn = createCn({
  extend: {
    classGroups: {
      "font-size": [
        {
          text: [
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "body-lg",
            "body-base",
            "body-sm",
            "label-md",
            "label-sm",
          ],
        },
      ],
    },
  },
});

export { cn };
