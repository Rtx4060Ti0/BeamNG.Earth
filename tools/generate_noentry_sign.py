"""Rebuild the no-entry face, reusing the existing sign body and face LODs."""
import json
from PIL import Image, ImageDraw
from generate_kmh_speed_signs import OUT, dae_xml, build_face_lods


def main():
    name = "sign_no_entry"
    img = Image.new("RGBA", (1024,1024), (255,255,255,0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((90,90,934,934), fill="white")
    draw.ellipse((104,104,920,920), fill=(205,20,30,255))
    draw.rectangle((205,435,819,589), fill="white")
    img.save(OUT / (name+".png"))
    (OUT/(name+".dae")).write_text(dae_xml(name,name+".png",build_face_lods()),encoding="utf-8")
    materials = json.loads((OUT/"sign_speed.materials.json").read_text(encoding="utf-8"))
    source = "sign_speed30kph"
    if source not in materials:
        raise RuntimeError("The existing 30 km/h face material is missing")
    material = json.loads(json.dumps(materials[source]).replace(source, name))
    (OUT/(name+".materials.json")).write_text(json.dumps({name:material},indent=2)+"\n",encoding="utf-8")


if __name__ == "__main__":
    main()
