import sys

from error import *
from llvmlite import ir, binding
import ctypes
import os

class COMPILER:
    def __init__(self, ast: list, file: str = ""):
        self.ast = ast
        self.file = file
        self.structs = {}
        self.stack = []
        self.context = []
        self.strings = {}
        self.functions = {}
        self.module = None
        self.error_class = ERROR()
        self.llvm_base_types = {
            "u8": ir.IntType(8),
            "u16": ir.IntType(16),
            "u32": ir.IntType(32),
            "u64": ir.IntType(64),
            "i8": ir.IntType(8),
            "i16": ir.IntType(16),
            "i32": ir.IntType(32),
            "i64": ir.IntType(64),
            "f32": ir.FloatType(),
            "f64": ir.DoubleType(),
            "string": ir.IntType(8).as_pointer(),
            "void": ir.VoidType()
        }

        self.init_bindings()
        self.create_module(file)

        for node in self.ast:
            self.compile_stmt(node)

        if len(self.error_class.stack) > 0:
            self.error_class.dump()

    def emit_obj(self, name):
        llvm_module = binding.parse_assembly(str(self.module))
        llvm_module.verify()

        target_triple = binding.get_default_triple()
        target = binding.Target.from_triple(target_triple)
        target_machine = target.create_target_machine(codemodel='default')
        obj = target_machine.emit_object(llvm_module)

        extension = ".obj" if sys.platform == "win32" else ".o"
        os.makedirs("_azure_temp_", exist_ok=True)
        obj_path = os.path.join("_azure_temp_", os.path.splitext(os.path.basename(name))[0] + extension)        
        with open(obj_path, "wb") as f:
            f.write(obj)
            f.close()
        return obj_path

    def init_bindings(self):
        binding.initialize_native_target()
        binding.initialize_native_asmprinter()

    def create_module(self, name: str = "main"):
        self.module = ir.Module(name=name)
        self.module.triple = binding.get_default_triple()
        self.module.data_layout = binding.Target.from_default_triple().create_target_machine(codemodel='default').target_data # type: ignore

    def get_context(self):
        if len(self.context) > 0:
            return self.context[len(self.context) - 1]
        else:
            return None

    def compile_type(self, node, value=None):
        if node["kind"] == "BaseType":
            return self.llvm_base_types[node["type"]]
        elif node["kind"] == "PointerType":
            inner = self.compile_type(node["to"], value)
            return inner.as_pointer()
        elif node["kind"] == "ArrayType":
            element = self.compile_type(node["of"], value)
            return (
                ir.ArrayType(element, node["size"])
                if node["size"] != None
                else element.as_pointer()
            )
        else:
            self.error_class.compiler_error("Uknown type!", self.file, node["line"])
            self.error_class.dump()

    def get_current_stack_frame(self, line: int = 1):
        if len(self.stack) > 0:
            return self.stack[len(self.stack) - 1]
        else:
            self.error_class.compiler_error(
                "Cannot declare variable outside of a scope!", self.file, line
            )
            self.error_class.dump()

    def compile_stmt(self, node):
        match node["kind"]:
            case "VariableDeclaration":
                return self.compile_variable(node)
            case "FunctionDeclaration":
                return self.compile_function(node)
            case "BinaryExpression":
                return self.compile_binary(node)
            case "IntegerLiteral" | "HexLiteral" | "OctalLiteral" | "BinaryLiteral":
                context = self.get_context()
                if context and context["kind"] in ("VariableDeclaration", "TypeCast"):
                    return ir.Constant(context["type"], node["value"])
                else:
                    return ir.Constant(ir.IntType(32), node["value"])
            case "IdentifierLiteral":
                stack_frame = self.get_current_stack_frame(node["line"])
                return stack_frame["builder"].load(stack_frame["variables"][node["value"]]["memory"])
            case "StringLiteral":
                return self.compile_string(node)
            case "ArrayLiteral":
                return self.compile_array(node)
            case "DeclareForeignStatement":
                return self.compile_declare_foreign(node)
            case "CallExpression":
                return self.compile_call(node)

    def retrieve_basic_type(self, node):
        if node["kind"] == "BaseType":
            return node["type"]
        elif node["kind"] == "ArrayType" or node["kind"] == "GenericType":
            return self.retrieve_basic_type(node["of"])
        elif node["kind"] == "PointerType":
            return self.retrieve_basic_type(node["to"])
        elif node["kind"] == "StructType":
            return node

    def compile_variable(self, node):
        stack_frame = self.get_current_stack_frame(node["line"])
        variable_type = self.compile_type(node["type"], node["value"])
        self.context.append({
            "kind": "VariableDeclaration",
            "type": variable_type,
            "raw": node["type"]
        })
        stack_frame["variables"][node["name"]] = {"memory": stack_frame["builder"].alloca(
            variable_type, name=node["name"]
        ), "type": node["type"]}
        stack_frame["builder"].store(self.compile_stmt(node["value"]), stack_frame["variables"][node["name"]]["memory"])
        self.context.pop()

    def compile_function(self, node):
        return_type = self.compile_type(node["return_type"])
        params = []
        for param in node["params"]:
            params.append(self.compile_type(param["type"]))
            
        func_type = ir.FunctionType(return_type, params)
        param_index = 0
        for param in node["params"]:
            func_type.args[param_index].name = param["name"]
            param_index += 1
        main_func = ir.Function(self.module, func_type, name=node["name"])
        
        block = main_func.append_basic_block(name="entry")
        builder = ir.IRBuilder(block)
        self.functions[node["name"]] = main_func
        self.stack.append({"builder": builder, "variables": {}})

        for body_node in node["body"]:
            self.compile_stmt(body_node)

        if len(node["body"]) == 0 or node["body"][len(node["body"]) - 1]["kind"] != "ReturnExpression":
            builder.ret(ir.Constant(return_type, 0))

        self.stack.pop()

    def compile_binary(self, node):
        left = self.compile_stmt(node["left"])
        right =  self.compile_stmt(node["right"])
        stack_frame = self.get_current_stack_frame(node["line"])
        result = None
        match node["operator"]:
            case "+":
                result = stack_frame["builder"].add(left, right)
            case "-":
                result = stack_frame["builder"].sub(left, right)
        return result
    
    def compile_string(self, node):   
        value = node["value"][1:-1]     
        if value in self.strings:
            return self.strings[value]
        
        stack_frame = self.get_current_stack_frame(node["line"])
        encoded = (value + "\0").encode("utf-8")
        string_type = ir.ArrayType(ir.IntType(8), len(encoded))
        
        global_var = ir.GlobalVariable(self.module, string_type, name=f".str.{len(self.strings)}")
        global_var.global_constant = True
        global_var.linkage = "internal"
        global_var.initializer = ir.Constant(string_type, bytearray(encoded)) # type: ignore
        
        zero = ir.Constant(ir.IntType(32), 0)
        string = stack_frame["builder"].gep(global_var, [zero, zero], inbounds=True)
        
        self.strings[value] = string
        return string
    
    def compile_array(self, node):
        # stack_frame = self.get_current_stack_frame(node["line"])
        elements_size = len(node["elements"])
        context = self.get_context()
        if context == None:
            return
        type_size = context["raw"]["size"]
        if type_size == None:
            type_size = 0
        
        if elements_size == 0 and type_size == 0:
            self.error_class.compiler_error("Array without a size must have atleast 1 element!", self.file, node["line"])
            self.error_class.dump()

        size = elements_size if elements_size > type_size else type_size
        element_type = self.compile_type(context["raw"]["of"])
        compiled_elements = []

        self.context.append({
            "kind": "TypeCast",
            "type": element_type,
            "raw": context["raw"]["of"]
        })

        for element in node["elements"]:
            compiled_elements.append(self.compile_stmt(element))

        self.context.pop()

        while len(compiled_elements) < size:
            compiled_elements.append(ir.Constant(element_type, 0))

        array_type = ir.ArrayType(element_type, size)
        return ir.Constant(array_type, compiled_elements)
    
    def compile_declare_foreign(self, node):
        if node["stmt"]["kind"] == "VariableDeclaration":
            counter = ir.GlobalVariable(self.module, self.compile_type(node["stmt"]["type"]), name=node["stmt"]["name"])
            counter.linkage = "external"
            counter.initializer = None
        elif node["stmt"]["kind"] == "FunctionDeclaration":     
            args = []
            varadic = False
            for arg in node["stmt"]["params"]:
                if arg["type"] == "varadic":
                    varadic = True
                    break
                args.append(self.compile_type(arg["type"]))
            func_type = ir.FunctionType(
                self.compile_type(node["stmt"]["return_type"]),
                args, var_arg=varadic
            )

            param_index = 0
            for param in node["stmt"]["params"]:
                if param["type"] == "varadic":
                    break
                func_type.args[param_index].name = param["name"]
                param_index += 1

            fn = ir.Function(self.module, func_type, name=node["stmt"]["name"])
            self.functions[node["stmt"]["name"]] = fn

    def compile_call(self, node):
        stack_frame = self.get_current_stack_frame(node["line"])
        function = self.functions[node["function"]]
        args = []

        for arg in node["args"]:
            args.append(self.compile_stmt(arg))

        return stack_frame["builder"].call(function, args)