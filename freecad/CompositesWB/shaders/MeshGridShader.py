from pivy import coin
from os import path
import FreeCADGui


def find_child(node, type_name):
    children = node.getChildren()

    if children is None or children.getLength() == 0:
        return None

    for child in children:
        if child.getTypeId().getName() == type_name:
            return child

    return None


def has_child(node, type_name):
    children = node.getChildren()

    if children is None or children.getLength() == 0:
        return None

    for child in children:
        if child.getTypeId().getName() == type_name:
            return node

        res = has_child(child, type_name)
        if res is not None:
            return res

    return None


def remove_by_name(node, name):
    item = node.getByName(name)
    if item:
        node.removeChild(item)
        return True
    return False


class MeshGridShader:
    shaderpath = path.dirname(path.abspath(__file__))

    def __init__(self):
        self.x_scale = coin.SoShaderParameter1f()
        self.x_scale.name = "x_scale"
        self.y_scale = coin.SoShaderParameter1f()
        self.y_scale.name = "y_scale"
        self.z_scale = coin.SoShaderParameter1f()
        self.z_scale.name = "z_scale"
        self.darken = coin.SoShaderParameter1f()
        self.darken.name = "darken"

        self.Spacing = [20.0, 2.0, 10.0]
        self.Darken = 0.1

        shader_params = [
            self.x_scale,
            self.y_scale,
            self.z_scale,
            self.darken,
        ]

        self.fragmentShader = coin.SoFragmentShader()
        self.fragmentShader.sourceProgram.setValue(
            path.join(MeshGridShader.shaderpath, "Grid_fragment_shader.glsl")
        )
        self.fragmentShader.parameter.setValues(
            0,
            len(shader_params),
            shader_params,
        )
        self.shaderProgram = coin.SoShaderProgram()
        self.shaderProgram.shaderObject.set1Value(0, self.fragmentShader)
        self.shaderProgram.setName("my_shader")
        self.texture = self.make_texture()

        self.grp = coin.SoGroup()
        self.grp.addChild(self.shaderProgram)
        self.grp.addChild(self.texture)

    def make_texture(self):
        fname = path.join(MeshGridShader.shaderpath, "brick.png")
        texture = coin.SoTexture3()
        texture.setName("my_texture")
        texture.filenames.set1Value(0, fname)
        return texture

    @property
    def Spacing(self):
        return [
            1.0 / self.x_scale.value.getValue(),
            1.0 / self.y_scale.value.getValue(),
            1.0 / self.z_scale.value.getValue(),
        ]

    @Spacing.setter
    def Spacing(self, v):
        self.x_scale.value = 1.0 / v[0]
        self.y_scale.value = 1.0 / v[1]
        self.z_scale.value = 1.0 / v[2]

    @property
    def Darken(self):
        return self.darken.value.getValue()

    @Darken.setter
    def Darken(self, v):
        self.darken.value = v

    @property
    def Root(self):
        return self.root

    def getTextureCoords(self, tex_coords):
        textureCoords = coin.SoTextureCoordinate3()
        textureCoords.setName("my_texcoord")
        if tex_coords is not None:
            for index, (s, t, q) in enumerate(tex_coords):
                textureCoords.point.set1Value(index, s, t, q)
        return textureCoords

    def detach(self, obj=None):
        self.attach(obj, None, None)

    def attach(self, obj, child, tex_coords=None):
        self.texcoords = self.getTextureCoords(tex_coords)

        if tex_coords is None:
            remove_by_name(self.grp, self.texcoords.getName())
            remove_by_name(self.grp, self.root.getName())
            return

        self.grp.addChild(self.texcoords)
        self.root = child.ViewObject.RootNode
        self.grp.addChild(self.root)

        switch = child.ViewObject.SwitchNode
        switch = self.root
        type_name = "SoFCIndexedFaceSet"
        node = has_child(switch, type_name)
        geom = find_child(node, type_name)
        if geom:
            coordinateIndex = geom.coordIndex.getValues()
            geom.textureCoordIndex.setValues(
                0,
                len(coordinateIndex),
                coordinateIndex,
            )

        # move the original node
        doc = obj.Document
        doc = FreeCADGui.getDocument(doc.Name)
        graph = doc.ActiveView.getSceneGraph()
        graph.removeChild(self.root)
