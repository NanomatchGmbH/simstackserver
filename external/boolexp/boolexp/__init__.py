from pyparsing import *
from math import floor


def convert_boolean(string, location, tokens):

    if tokens[0] == 'True':
        return True
    elif tokens[0] == 'False':
        return False

def convert_expression(string, location, t):

    if len(t) == 1:
        return t[0]

    elif len(t) == 3:
        return Operator(t[1],t[0],t[2])

    else:
        raise Exception(t)

def convert_not_expression(string, location, t):

    if len(t) == 1:
        return t

    if len(t) == 2 and t[0] == 'not':
        return NotOperator(t[1])

    else:
        raise Exception(t)

def convert_upper_lower(string, location, tokens):

    if len(tokens) == 2:
        if tokens[1] == 'upper':
            return UpperModificator(tokens[0])

        elif tokens[1] == 'lower':
            return LowerModificator(tokens[0])
   
    else:
        raise Exception(tokens)
        

def convert_split_strip(self, location, tokens):

    if not len(tokens) in [2,3]:
        raise Exception(tokens)

    arg = ' '
    if len(tokens) == 3:
        arg = tokens[2]

    if tokens[1] == 'split':
        return SplitModificator(tokens[0], arg)

    elif tokens[1] == 'strip':
        return StripModificator(tokens[0], arg)

   

class Constant(object):
    
    def __init__(self, constant):
        self.constant = constant
        
    def get_value(self, context):
        return self.constant


class Variable(object):

    def __init__(self, tokens):
        self.parts = tokens

    def get_value(self, context):
        result = context

        for p in self.parts:
            result = result[p]

        return result

class Array(object):

    def __init__(self,tokens):
        self.parts = tokens

    def get_value(self, context):
        result = []

        for p in self.parts:
            result.append(p.get_value(context))

        return result

class NotOperator(object):
    
    def __init__(self, operand):
        self.operand = operand

    def get_value(self, context):
        return not self.operand.get_value(context)


class Operator(object):

    def __init__(self, operator, left, right):
        self.left = left
        self.right = right
        self.operator = operator
   
    def get_value(self, context):

        if self.operator == '==':
            return self.left.get_value(context) == self.right.get_value(context)

        elif self.operator == '!=':
            return self.left.get_value(context) != self.right.get_value(context)
       
        elif self.operator == '<':
            return self.left.get_value(context) < self.right.get_value(context)

        elif self.operator == '>':
            return self.left.get_value(context) > self.right.get_value(context)

        elif self.operator == '<=':
            return self.left.get_value(context) <= self.right.get_value(context)

        elif self.operator == '>=':
            return self.left.get_value(context) >= self.right.get_value(context)

        if self.operator == 'and':
            #TODO: not evaluate second operand unil first is false
            left = self.left.get_value(context)

            if type(left) == bool:

                if left:  
                    right = self.right.get_value(context)
                    if type(right) == bool:
                        return right

                    else:
                        raise
            else:
                raise

        if self.operator == 'or':
            left = self.left.get_value(context)
            right = self.right.get_value(context)

            if self.ensure_bool(left, right):
                return (left or right)
            else:
                raise

        if self.operator == 'in':
            #if type(right) == list or type(right) == set:
            return self.left.get_value(context) in self.right.get_value(context)
                    
        if self.operator == '+':
            left = self.left.get_value(context)
            right = self.right.get_value(context)

            if not type(left) in (int,float):
                raise ValueError("left argument of + operator must be integer or float")
            
            if not type(right) in (int,float):
                raise ValueError("right argument of + operator must be integer or float")
            
            return left + right

        if self.operator == '-':
            left = self.left.get_value(context)
            right = self.right.get_value(context)

            if not type(left) in (int,float):
                raise ValueError("left argument of - operator must be integer or float")
            
            if not type(right) in (int,float):
                raise ValueError("right argument of - operator must be integer or float")
            
            return left - right

        if self.operator == '*':
            left = self.left.get_value(context)
            right = self.right.get_value(context)

            if not type(left) in (int,float):
                raise ValueError("left argument of * operator must be integer or float")
            
            if not type(right) in (int,float):
                raise ValueError("right argument of * operator must be integer or float")
            
            return left * right

        if self.operator == '/':
            left = self.left.get_value(context)
            right = self.right.get_value(context)

            if not type(left) in (int,float):
                raise ValueError("left argument of * operator must be integer or float")
            
            if not type(right) in (int,float):
                raise ValueError("right argument of * operator must be integer or float")
            
            result = float(left) / right

            floor_result = floor(result)

            if floor_result == result:
                return floor_result
            else:
                return result


    def ensure_bool(self,left,right):

        if type(left) == bool and type(right) == bool:
            return True
        else:
            return False

class LowerModificator(object):
    
    def __init__(self, value):
        self.value = value

    def get_value(self, context):
        string = self.value.get_value(context)
        
        if type(string) == str:
            return string.lower()
        else:
            raise ValueError("Lower modificator can convert only strings")


class UpperModificator(object):
    
    def __init__(self, value):
        self.value = value

    def get_value(self, context):
        string = self.value.get_value(context)
        
        if type(string) == str:
            return string.upper()
        else:
            raise ValueError("Upper modificator can convert only strings")


class StripModificator(object):
    
    def __init__(self, value, argument):
        self.value = value
        self.argument = argument

    def get_value(self, context):
        string = self.value.get_value(context)
        
        if type(string) == str and type(self.argument) == str:
            return string.strip(self.argument)

        else:
            raise ValueError("Strip modificator can convert only strings")


class SplitModificator(object):
    
    def __init__(self, value, argument):
        self.value = value
        self.argument = argument

    def get_value(self, context):
        string = self.value.get_value(context)
        
        if type(string) == str and type(self.argument) == str:
            return string.split(self.argument)

        else:
            raise ValueError("Split modificator can convert only strings")


class Grammar(object):

    #number constants
    plusorminus = Literal('+') | Literal('-')
    point = Literal('.')
    dot = Literal('.').suppress()
    bar = Literal('|').suppress()
    comma = Literal(',').suppress()
    larray = Literal('[').suppress()
    rarray = Literal(']').suppress()
    lbracket = Literal('(').suppress()
    rbracket = Literal(')').suppress()

    string_lower = Literal('lower')
    string_upper = Literal('upper')
    string_split = Literal('split')
    string_strip = Literal('strip')

    integer = Optional(plusorminus) + Word(nums)
    integer.setParseAction(lambda s,l,t: int(''.join(t)))

    floatnumber = Combine( integer + point + Word(nums) )
    floatnumber.setParseAction(lambda s,l,t: float(t[0]))

    number = floatnumber | integer

    #boolean constants
    boolean = Literal('True') | Literal('False')
    boolean.setParseAction(convert_boolean)

    #string constants
    string = dblQuotedString | quotedString
    string.setParseAction(removeQuotes)

    array_of_numbers =  Literal('[') 
    array_of_strings =  Literal('[') 

    constant = number | boolean | string 
    constant.setParseAction(lambda s,l,t: Constant(t[0]))

    # array
    empty_array = larray + rarray
    array = empty_array | (larray + OneOrMore(constant + ZeroOrMore(comma)) + rarray)
    array.setParseAction(lambda s,l,t: Array(t))

    #variable name
    name = Word( alphas+"_", alphanums+"_" )

    #array_access
    array_access = name + OneOrMore(
        larray + integer + rarray)

    #variable atom TODO: find better expression
    variable_atom = array_access | name

    variable = variable_atom + ZeroOrMore( 
        dot + variable_atom)
    variable.leaveWhitespace()
    variable.setParseAction(lambda s,l,t: Variable(t))

    upper_lower_exp = (string | variable) + bar + (string_lower | string_upper)
    upper_lower_exp.addParseAction(convert_upper_lower)

    split_strip_exp = (string | variable) + bar + (string_split | string_strip) + lbracket + Optional(string) + rbracket
    split_strip_exp.addParseAction(convert_split_strip)

    operand = split_strip_exp | upper_lower_exp | constant | variable | array

    prio_expression = Forward()
    atom_expression = operand | prio_expression

    operator = oneOf("* /")
    muldiv_exp = Forward()
    muldiv_exp << atom_expression + Optional(operator + muldiv_exp)
    muldiv_exp.addParseAction(convert_expression)

    operator = oneOf("+ -")
    addsub_exp = Forward()
    addsub_exp << muldiv_exp + Optional(operator + addsub_exp)
    addsub_exp.addParseAction(convert_expression)

    operator = oneOf("!= == < > <= >= in")
    comparsion_exp = Forward()
    comparsion_exp << addsub_exp + Optional(operator + comparsion_exp)
    comparsion_exp.addParseAction(convert_expression)

    operator = Literal('not')
    not_exp = Forward()
    not_exp <<  Optional(operator) + comparsion_exp
    not_exp.addParseAction(convert_not_expression)

    operator = oneOf("and or")
    expression = Forward()
    expression << not_exp + Optional(operator + expression)

    prio_expression << lbracket + expression + rbracket
    prio_expression.addParseAction(convert_expression)

    final_expression = expression | prio_expression + StringEnd()

    def parse(self, expr):
        result = self.final_expression.parseString(expr)
        return result[0]


class Expression(object):

    grammar = Grammar()

    def __init__(self, exp):
        self.expression = exp

    def evaluate(self, context = {}):
        self.context = context
        expression_root = self.grammar.parse(self.expression)
        value =  expression_root.get_value(context)
        return value


