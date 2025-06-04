## Minecraft TTF

This python script converts Minecraft: Java Edition [font definition files](https://minecraft.wiki/w/Font#Providers) to [TrueType Fonts (TTFs)](https://en.wikipedia.org/wiki/TrueType).

By default, the script downloads the latest snapshot jar, reads all the font definitions, and generates regular, bold, italic, and bold italic font files corresponding to each. Currently, that includes `default` (the normal game font), `alt` (the enchantment table font), `illageralt` (an unused font from Minecraft Dungeons), and `uniform` (which is empty, see below).

Other Minecraft TTFs floating around tend to be outdated (using the pre-1.13 bitmap) or don't contain the complete set of characters. Using this script will ensure you have a perfectly matching set.

The `ttf` and `unihex` providers are not supported. Vanilla does not use the `ttf` provider, but it does use the `unihex` provider to create the `uniform` font and add fallbacks to the `default` font. Merging in the entirety of [GNU Unifont](https://en.wikipedia.org/wiki/GNU_Unifont) is useful for vanilla text, but is contrary to the goals of this project.
